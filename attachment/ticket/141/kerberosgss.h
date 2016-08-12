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

//#include <gssapi/gssapi.h>
//#include <gssapi/gssapi_generic.h>
//#include <gssapi/gssapi_krb5.h>
#include <Kerberos/Kerberos.h>

#define krb5_get_err_text(context,code) error_message(code)

#define AUTH_GSS_ERROR		-1
#define AUTH_GSS_COMPLETE	1
#define AUTH_GSS_CONTINUE	0

typedef struct {
	gss_ctx_id_t    context;
	gss_name_t		server_name;
	char*			username;
	char*			response;
	gss_cred_id_t	client_credentials;
} gss_client_state;

typedef struct {
	gss_ctx_id_t    context;
	gss_name_t		server_name;
	gss_name_t		client_name;
    gss_cred_id_t	server_creds;
    gss_cred_id_t	client_creds;
	char*			username;
	char*			response;
} gss_server_state;

int authenticate_gss_client_init(const char* client, const char* service, gss_client_state *state);
int authenticate_gss_client_clean(gss_client_state *state);
int authenticate_gss_client_step(gss_client_state *state, const char *challenge);

int authenticate_gss_server_init(const char* service, gss_server_state *state);
int authenticate_gss_server_clean(gss_server_state *state);
int authenticate_gss_server_step(gss_server_state *state, const char *challenge);
