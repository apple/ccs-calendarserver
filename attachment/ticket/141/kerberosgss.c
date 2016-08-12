/**
 * Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * DRI: Cyrus Daboo, cdaboo@apple.com
 **/

//#include <Python.h>
#include "kerberosgss.h"

#include "base64.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void set_gss_error(OM_uint32 err_maj, OM_uint32 err_min);

//extern PyObject *GssException_class;
//extern PyObject *KrbException_class;

int authenticate_gss_client_init(const char* inClientName, const char* inServiceName, gss_client_state *state)
{
    int err = 0;
    OM_uint32 majorStatus;
    OM_uint32 minorStatus = 0;
    gss_name_t clientName;
	state->client_credentials = GSS_C_NO_CREDENTIAL;
	state->context = GSS_C_NO_CONTEXT;
    
    if (!err) {
        if (inClientName != NULL) {
            gss_buffer_desc nameBuffer = { strlen (inClientName), (char *) inClientName };
            
            majorStatus = gss_import_name (&minorStatus, &nameBuffer, GSS_C_NT_USER_NAME, &clientName); 
            if (majorStatus != GSS_S_COMPLETE) { 
				set_gss_error(majorStatus, minorStatus);
                err = minorStatus ? minorStatus : majorStatus; 
            }
        
            if (!err) {
                majorStatus = gss_acquire_cred (&minorStatus, clientName, GSS_C_INDEFINITE, GSS_C_NO_OID_SET, 
                                                GSS_C_INITIATE, &state->client_credentials, NULL, NULL); 
                if (majorStatus != GSS_S_COMPLETE) { 
					set_gss_error(majorStatus, minorStatus);
					err = minorStatus ? minorStatus : majorStatus; 
                }
            }
        }
    }
    
    if (!err) {
        gss_buffer_desc nameBuffer = { strlen (inServiceName), (char *) inServiceName };
        
        majorStatus = gss_import_name (&minorStatus, &nameBuffer, (gss_OID) GSS_KRB5_NT_PRINCIPAL_NAME, &state->server_name); 
        if (majorStatus != GSS_S_COMPLETE) { 
			set_gss_error(majorStatus, minorStatus);
            err = minorStatus ? minorStatus : majorStatus; 
        }
    }

    if (clientName != NULL) { gss_release_name (&minorStatus, &clientName); }

    return err;

}

int authenticate_gss_client_clean(gss_client_state *state)
{
	OM_uint32 maj_stat;
	OM_uint32 min_stat;
	int ret = AUTH_GSS_COMPLETE;
	
	if (state->context != GSS_C_NO_CONTEXT)
		maj_stat = gss_delete_sec_context(&min_stat, &state->context, GSS_C_NO_BUFFER);
	if (state->server_name != GSS_C_NO_NAME)
		maj_stat = gss_release_name(&min_stat, &state->server_name);
	if (state->username != NULL)
	{
		free(state->username);
		state->username = NULL;
	}
	if (state->response != NULL)
	{
		free(state->response);
		state->response = NULL;
	}
	
	return ret;
}

int authenticate_gss_client_step(gss_client_state *state, const char *challenge)
{
	// new
    int err = 0;
    OM_uint32 majorStatus;
    OM_uint32 minorStatus = 0;
    OM_uint32 actualFlags = 0;
    gss_buffer_desc inputToken;  /* buffer received from the server */
    gss_buffer_t inputTokenPtr = GSS_C_NO_BUFFER;
    
	// Always clear out the old response
	if (state->response != NULL) {
		free(state->response);
		state->response = NULL;
	}
	   
	// If there is a challenge (data from the server) we need to give it to GSS
	if (challenge && *challenge) {
		int len;
		inputToken.value = base64_decode(challenge, &len);
		inputToken.length = len;
		inputTokenPtr = &inputToken;
	}
	   
	gss_buffer_desc outputToken = { 0, NULL }; /* buffer to send to the server */
	OM_uint32 requestedFlags = (GSS_C_MUTUAL_FLAG | GSS_C_REPLAY_FLAG | GSS_C_SEQUENCE_FLAG | 
								GSS_C_CONF_FLAG | GSS_C_INTEG_FLAG);
	
	majorStatus = gss_init_sec_context (&minorStatus, state->client_credentials, &state->context, state->server_name, 
										GSS_C_NULL_OID /* mech_type */, requestedFlags, GSS_C_INDEFINITE, 
										GSS_C_NO_CHANNEL_BINDINGS, inputTokenPtr,
										NULL /* actual_mech_type */, &outputToken, 
										&actualFlags, NULL /* time_rec */);

	if ((majorStatus != GSS_S_COMPLETE) && (majorStatus != GSS_S_CONTINUE_NEEDED)) {
		set_gss_error(majorStatus, minorStatus);
		err = AUTH_GSS_ERROR;
		goto end;
	}


	if ((outputToken.length > 0) && (outputToken.value != NULL)) {
		state->response = base64_encode((const unsigned char *)outputToken.value, outputToken.length);;
		err = gss_release_buffer(&minorStatus, &outputToken);
		if (err != GSS_S_CONTINUE_NEEDED && err != GSS_S_COMPLETE) {
			set_gss_error(err, minorStatus);
			err = minorStatus ? minorStatus : err; 
			goto end;
        }
	}
	
	// Try to get the user name if we have completed all GSS operations
	if (majorStatus == GSS_S_COMPLETE) {
	
		gss_name_t gssuser = GSS_C_NO_NAME;
		majorStatus = gss_inquire_context(&minorStatus, state->context, &gssuser, NULL, NULL, NULL,  NULL, NULL, NULL);
		if (GSS_ERROR(majorStatus))
		{
			set_gss_error(majorStatus, minorStatus);
			err = AUTH_GSS_ERROR;
			goto end;
		}
		
		gss_buffer_desc name_token;
		name_token.length = 0;
		majorStatus = gss_display_name(&minorStatus, gssuser, &name_token, NULL);
		if (GSS_ERROR(majorStatus))
		{
			if (name_token.value)
				gss_release_buffer(&minorStatus, &name_token);
			gss_release_name(&minorStatus, &gssuser);
			
			set_gss_error(majorStatus, minorStatus);
			err = AUTH_GSS_ERROR;
			goto end;
		}
		else
		{
			state->username = (char *)malloc(name_token.length + 1);
			strncpy(state->username, (char*) name_token.value, name_token.length);
			state->username[name_token.length] = 0;
			gss_release_buffer(&minorStatus, &name_token);
			gss_release_name(&minorStatus, &gssuser);
		}
	}
	
	end:
	if (outputToken.value) {
		gss_release_buffer(&minorStatus, &outputToken);
	}

	return majorStatus;
}

int authenticate_gss_server_clean(gss_server_state *state)
{
	OM_uint32 maj_stat;
	OM_uint32 min_stat;
	int ret = AUTH_GSS_COMPLETE;
	
	if (state->context != GSS_C_NO_CONTEXT)
		maj_stat = gss_delete_sec_context(&min_stat, &state->context, GSS_C_NO_BUFFER);
	if (state->server_name != GSS_C_NO_NAME)
		maj_stat = gss_release_name(&min_stat, &state->server_name);
	if (state->client_name != GSS_C_NO_NAME)
		maj_stat = gss_release_name(&min_stat, &state->client_name);
	if (state->server_creds != GSS_C_NO_CREDENTIAL)
		maj_stat = gss_release_cred(&min_stat, &state->server_creds);
	if (state->client_creds != GSS_C_NO_CREDENTIAL)
		maj_stat = gss_release_cred(&min_stat, &state->client_creds);
	if (state->username != NULL)
	{
		free(state->username);
		state->username = NULL;
	}
	if (state->response != NULL)
	{		
		free(state->response);
		state->response = NULL;
	}
	
	return ret;
}

int authenticate_gss_server_step(gss_server_state *state, const char *challenge)
{
	OM_uint32 maj_stat;
	OM_uint32 min_stat;
	gss_buffer_desc input_token = GSS_C_EMPTY_BUFFER;
	gss_buffer_desc output_token = GSS_C_EMPTY_BUFFER;
	int ret = AUTH_GSS_CONTINUE;
	
	// Always clear out the old response
	if (state->response != NULL)
	{
		free(state->response);
		state->response = NULL;
	}
	
	// If there is a challenge (data from the server) we need to give it to GSS
	if (challenge && *challenge)
	{
		int len;
		input_token.value = base64_decode(challenge, &len);
		input_token.length = len;
	}
	else
	{
		//PyErr_SetString(KrbException_class, "No challenge parameter in request from client");
		ret = AUTH_GSS_ERROR;
		goto end;
	}
	
	maj_stat = gss_accept_sec_context(&min_stat,
										&state->context,
										state->server_creds,
										&input_token,
										GSS_C_NO_CHANNEL_BINDINGS,
										&state->client_name,
										NULL,
										&output_token,
										NULL,
										NULL,
										&state->client_creds);
	
	if (GSS_ERROR(maj_stat))
	{
		set_gss_error(maj_stat, min_stat);
		ret = AUTH_GSS_ERROR;
		goto end;
	}
	
	// Grab the server response to send back to the client
	if (output_token.length)
	{
		state->response = base64_encode((const unsigned char *)output_token.value, output_token.length);;
		maj_stat = gss_release_buffer(&min_stat, &output_token);
	}
	
	maj_stat = gss_display_name(&min_stat, state->client_name, &output_token, NULL);
	if (GSS_ERROR(maj_stat))
	{
		set_gss_error(maj_stat, min_stat);
		ret = AUTH_GSS_ERROR;
		goto end;
	}
	state->username = (char *)malloc(output_token.length + 1);
	strncpy(state->username, (char*) output_token.value, output_token.length);
	state->username[output_token.length] = 0;
	
	ret = AUTH_GSS_COMPLETE;
	
	end:
	if (output_token.length) {
		gss_release_buffer(&min_stat, &output_token);
	}
	if (input_token.value) {
		free(input_token.value);
	}
	return ret;
}


static void set_gss_error(OM_uint32 err_maj, OM_uint32 err_min)
{
	OM_uint32 maj_stat, min_stat;
	OM_uint32 msg_ctx = 0;
	gss_buffer_desc status_string;
	char buf_maj[512];
	char buf_min[512];
	
	do
	{
		maj_stat = gss_display_status (&min_stat,
		err_maj,
		GSS_C_GSS_CODE,
		GSS_C_NO_OID,
		&msg_ctx,
		&status_string);
		if (GSS_ERROR(maj_stat))
			break;
		strncpy(buf_maj, (char*) status_string.value, sizeof(buf_maj));
		gss_release_buffer(&min_stat, &status_string);
		
		maj_stat = gss_display_status (&min_stat,
		err_min,
		GSS_C_MECH_CODE,
		GSS_C_NULL_OID,
		&msg_ctx,
		&status_string);
		if (!GSS_ERROR(maj_stat))
		{
			strncpy(buf_min, (char*) status_string.value, sizeof(buf_min));
			gss_release_buffer(&min_stat, &status_string);
		}
	} while (!GSS_ERROR(maj_stat) && msg_ctx != 0);
	
	//PyErr_SetObject(GssException_class, Py_BuildValue("((s:i)(s:i))", buf_maj, err_maj, buf_min, err_min));
	printf("((%s:%i)(%s:%i))\n", buf_maj, err_maj, buf_min, err_min);
	
}
