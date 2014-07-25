# #
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# #

"""
Record types and attribute names from Directory Service.
This comes directly (with C->Python conversion) from <DirectoryServices/DirServicesConst.h>
"""

# Specific match types

eDSExact = 0x2001
eDSStartsWith = 0x2002
eDSEndsWith = 0x2003
eDSContains = 0x2004

eDSLessThan = 0x2005
eDSGreaterThan = 0x2006
eDSLessEqual = 0x2007
eDSGreaterEqual = 0x2008

# Specific Record Type Constants

"""
 DirectoryService Specific Record Type Constants
"""

"""
 kDSStdRecordTypeAccessControls
  Record type that contains directory access control directives.
"""
kDSStdRecordTypeAccessControls = "dsRecTypeStandard:AccessControls"

"""
 kDSStdRecordTypeAFPServer
  Record type of AFP server records.
"""
kDSStdRecordTypeAFPServer = "dsRecTypeStandard:AFPServer"

"""
 kDSStdRecordTypeAFPUserAliases
  Record type of AFP user aliases used exclusively by AFP processes.
"""
kDSStdRecordTypeAFPUserAliases = "dsRecTypeStandard:AFPUserAliases"

"""
 kDSStdRecordTypeAliases
  Used to represent alias records.
"""
kDSStdRecordTypeAliases = "dsRecTypeStandard:Aliases"

"""
 kDSStdRecordTypeAugments
  Used to store augmented record data.
"""
kDSStdRecordTypeAugments = "dsRecTypeStandard:Augments"

"""
 kDSStdRecordTypeAutomount
  Used to store automount record data.
"""
kDSStdRecordTypeAutomount = "dsRecTypeStandard:Automount"

"""
 kDSStdRecordTypeAutomountMap
  Used to store automountMap record data.
"""
kDSStdRecordTypeAutomountMap = "dsRecTypeStandard:AutomountMap"

"""
 kDSStdRecordTypeAutoServerSetup
  Used to discover automated server setup information.
"""
kDSStdRecordTypeAutoServerSetup = "dsRecTypeStandard:AutoServerSetup"

"""
 kDSStdRecordTypeBootp
  Record in the local node for storing bootp info.
"""
kDSStdRecordTypeBootp = "dsRecTypeStandard:Bootp"

"""
 kDSStdRecordTypeCertificateAuthority
  Record type that contains certificate authority information.
"""
kDSStdRecordTypeCertificateAuthorities = "dsRecTypeStandard:CertificateAuthorities"

"""
 kDSStdRecordTypeComputerLists
  Identifies computer list records.
"""
kDSStdRecordTypeComputerLists = "dsRecTypeStandard:ComputerLists"

"""
 kDSStdRecordTypeComputerGroups
  Identifies computer group records.
"""
kDSStdRecordTypeComputerGroups = "dsRecTypeStandard:ComputerGroups"

"""
 kDSStdRecordTypeComputers
  Identifies computer records.
"""
kDSStdRecordTypeComputers = "dsRecTypeStandard:Computers"

"""
 kDSStdRecordTypeConfig
  Identifies config records.
"""
kDSStdRecordTypeConfig = "dsRecTypeStandard:Config"

"""
 kDSStdRecordTypeEthernets
  Record in the local node for storing ethernets.
"""
kDSStdRecordTypeEthernets = "dsRecTypeStandard:Ethernets"

"""
 kDSStdRecordTypeFileMakerServers
  FileMaker servers record type. Describes available FileMaker servers,
  used for service discovery.
"""
kDSStdRecordTypeFileMakerServers = "dsRecTypeStandard:FileMakerServers"

"""
 kDSStdRecordTypeFTPServer
  Identifies ftp server records.
"""
kDSStdRecordTypeFTPServer = "dsRecTypeStandard:FTPServer"

"""
 kDSStdRecordTypeGroupAliases
  No longer supported in Mac OS X 10.4 or later.
"""
kDSStdRecordTypeGroupAliases = "dsRecTypeStandard:GroupAliases"

"""
 kDSStdRecordTypeGroups
  Identifies group records.
"""
kDSStdRecordTypeGroups = "dsRecTypeStandard:Groups"

"""
 kDSStdRecordTypeHostServices
  Record in the local node for storing host services.
"""
kDSStdRecordTypeHostServices = "dsRecTypeStandard:HostServices"

"""
 kDSStdRecordTypeHosts
  Identifies host records.
"""
kDSStdRecordTypeHosts = "dsRecTypeStandard:Hosts"

"""
 kDSStdRecordTypeLDAPServer
  Identifies LDAP server records.
"""
kDSStdRecordTypeLDAPServer = "dsRecTypeStandard:LDAPServer"

"""
 kDSStdRecordTypeLocations
  Location record type.
"""
kDSStdRecordTypeLocations = "dsRecTypeStandard:Locations"

"""
 kDSStdRecordTypeMachines
  Identifies machine records.
"""
kDSStdRecordTypeMachines = "dsRecTypeStandard:Machines"

"""
 kDSStdRecordTypeMaps
  Identifies map records.
"""
kDSStdRecordTypeMaps = "dsRecTypeStandard:Maps"

"""
 kDSStdRecordTypeMeta
  Identifies meta records.
"""
kDSStdRecordTypeMeta = "dsRecTypeStandard:AppleMetaRecord"

"""
 kDSStdRecordTypeMounts
  Identifies mount records.
"""
kDSStdRecordTypeMounts = "dsRecTypeStandard:Mounts"

"""
 kDSStdRecordTypMounts
  Supported only for backward compatibility to kDSStdRecordTypeMounts.
"""
kDSStdRecordTypMounts = "dsRecTypeStandard:Mounts"

"""
 kDSStdRecordTypeNeighborhoods
  Neighborhood record type. Describes a list of computers and other
  neighborhoods, used for network browsing.
"""
kDSStdRecordTypeNeighborhoods = "dsRecTypeStandard:Neighborhoods"

"""
 kDSStdRecordTypeNFS
  Identifies NFS records.
"""
kDSStdRecordTypeNFS = "dsRecTypeStandard:NFS"

"""
 kDSStdRecordTypeNetDomains
  Record in the local node for storing net domains.
"""
kDSStdRecordTypeNetDomains = "dsRecTypeStandard:NetDomains"

"""
 kDSStdRecordTypeNetGroups
  Record in the local node for storing net groups.
"""
kDSStdRecordTypeNetGroups = "dsRecTypeStandard:NetGroups"

"""
 kDSStdRecordTypeNetworks
  Identifies network records.
"""
kDSStdRecordTypeNetworks = "dsRecTypeStandard:Networks"

"""
 kDSStdRecordTypePasswordServer
  Used to discover password servers via Bonjour.
"""
kDSStdRecordTypePasswordServer = "dsRecTypeStandard:PasswordServer"

"""
 kDSStdRecordTypePeople
  Record type that contains "People" records used for contact information.
"""
kDSStdRecordTypePeople = "dsRecTypeStandard:People"

"""
 kDSStdRecordTypePlaces
  Identifies places (rooms) records.
"""
kDSStdRecordTypePlaces = "dsRecTypeStandard:Places"

"""
 kDSStdRecordTypePresetComputers
  The computer record type used for presets in record creation.
"""
kDSStdRecordTypePresetComputers = "dsRecTypeStandard:PresetComputers"

"""
 kDSStdRecordTypePresetComputerGroups
  The computer group record type used for presets in record creation.
"""
kDSStdRecordTypePresetComputerGroups = "dsRecTypeStandard:PresetComputerGroups"

"""
 kDSStdRecordTypePresetComputerLists
  The computer list record type used for presets in record creation.
"""
kDSStdRecordTypePresetComputerLists = "dsRecTypeStandard:PresetComputerLists"

"""
 kDSStdRecordTypePresetGroups
  The group record type used for presets in record creation.
"""
kDSStdRecordTypePresetGroups = "dsRecTypeStandard:PresetGroups"

"""
 kDSStdRecordTypePresetUsers
  The user record type used for presets in record creation.
"""
kDSStdRecordTypePresetUsers = "dsRecTypeStandard:PresetUsers"

"""
 kDSStdRecordTypePrintService
  Identifies print service records.
"""
kDSStdRecordTypePrintService = "dsRecTypeStandard:PrintService"

"""
 kDSStdRecordTypePrintServiceUser
  Record in the local node for storing quota usage for a user.
"""
kDSStdRecordTypePrintServiceUser = "dsRecTypeStandard:PrintServiceUser"

"""
 kDSStdRecordTypePrinters
  Identifies printer records.
"""
kDSStdRecordTypePrinters = "dsRecTypeStandard:Printers"

"""
 kDSStdRecordTypeProtocols
  Identifies protocol records.
"""
kDSStdRecordTypeProtocols = "dsRecTypeStandard:Protocols"

"""
 kDSStdRecordTypProtocols
  Supported only for backward compatibility to kDSStdRecordTypeProtocols.
"""
kDSStdRecordTypProtocols = "dsRecTypeStandard:Protocols"

"""
 kDSStdRecordTypeQTSServer
  Identifies quicktime streaming server records.
"""
kDSStdRecordTypeQTSServer = "dsRecTypeStandard:QTSServer"

"""
 kDSStdRecordTypeResources
  Identifies resources used in group services.
"""
kDSStdRecordTypeResources = "dsRecTypeStandard:Resources"

"""
 kDSStdRecordTypeRPC
  Identifies remote procedure call records.
"""
kDSStdRecordTypeRPC = "dsRecTypeStandard:RPC"

"""
 kDSStdRecordTypRPC
  Supported only for backward compatibility to kDSStdRecordTypeRPC.
"""
kDSStdRecordTypRPC = "dsRecTypeStandard:RPC"

"""
 kDSStdRecordTypeSMBServer
  Identifies SMB server records.
"""
kDSStdRecordTypeSMBServer = "dsRecTypeStandard:SMBServer"

"""
 kDSStdRecordTypeServer
  Identifies generic server records.
"""
kDSStdRecordTypeServer = "dsRecTypeStandard:Server"

"""
 kDSStdRecordTypeServices
  Identifies directory based service records.
"""
kDSStdRecordTypeServices = "dsRecTypeStandard:Services"

"""
 kDSStdRecordTypeSharePoints
  Share point record type.
"""
kDSStdRecordTypeSharePoints = "dsRecTypeStandard:SharePoints"

"""
 kDSStdRecordTypeUserAliases
  No longer supported in Mac OS X 10.4 or later.
"""
kDSStdRecordTypeUserAliases = "dsRecTypeStandard:UserAliases"

"""
 kDSStdRecordTypeUsers
  Identifies user records.
"""
kDSStdRecordTypeUsers = "dsRecTypeStandard:Users"

"""
 kDSStdRecordTypeWebServer
  Identifies web server records.
"""
kDSStdRecordTypeWebServer = "dsRecTypeStandard:WebServer"

# Specific Attribute Type Constants


"""
 DirectoryService Specific Attribute Type Constants
 As a guideline for the attribute types the following legend is used:

        eDS1xxxxxx  Single Valued Attribute

        eDSNxxxxxx  Multi-Valued Attribute

    NOTE #1: Access controls may prevent any particular client from reading/writing
            various attribute types.  In addition some attribute types may not be stored at
            all and could also represent "real-time" data generated by the directory node
            plug-in.

    NOTE #2: Attributes in the model are available for records and directory nodes.
"""


# Single Valued Specific Attribute Type Constants


"""
 DirectoryService Single Valued Specific Attribute Type Constants
"""

"""
    kDS1AttrAdminLimits
    XML plist indicating what an admin user can edit.
        Found in kDSStdRecordTypeUsers records.
"""
kDS1AttrAdminLimits = "dsAttrTypeStandard:AdminLimits"

"""
 kDS1AttrAliasData
 Used to identify alias data.
"""
kDS1AttrAliasData = "dsAttrTypeStandard:AppleAliasData"

"""
 kDS1AttrAlternateDatastoreLocation
 Unix path used for determining where a user's email is stored.
"""
kDS1AttrAlternateDatastoreLocation = "dsAttrTypeStandard:AlternateDatastoreLocation"

"""
 kDS1AttrAuthenticationHint
 Used to identify the authentication hint phrase.
"""
kDS1AttrAuthenticationHint = "dsAttrTypeStandard:AuthenticationHint"

"""
 kDSNAttrAttributeTypes
 Used to indicated recommended attribute types for a record type in the Config node.
"""
kDSNAttrAttributeTypes = "dsAttrTypeStandard:AttributeTypes"

"""
 kDS1AttrAuthorityRevocationList
 Attribute containing the binary of the authority revocation list.
 A certificate revocation list that defines certificate authority certificates
 which are no longer trusted.  No user certificates are included in this list.
 Usually found in kDSStdRecordTypeCertificateAuthority records.
"""
kDS1AttrAuthorityRevocationList = "dsAttrTypeStandard:AuthorityRevocationList"

"""
 kDS1AttrBirthday
 Single-valued attribute that defines the user's birthday.
 Format is x.208 standard YYYYMMDDHHMMSSZ which we will require as GMT time.
"""
kDS1AttrBirthday = "dsAttrTypeStandard:Birthday"


"""
 kDS1AttrBootFile
 Attribute type in host or machine records for the name of the
        kernel that this machine will use by default when NetBooting.
"""
kDS1AttrBootFile = "dsAttrTypeStandard:BootFile"

"""
 kDS1AttrCACertificate
 Attribute containing the binary of the certificate of a
 certificate authority. Its corresponding private key is used to sign certificates.
 Usually found in kDSStdRecordTypeCertificateAuthority records.
"""
kDS1AttrCACertificate = "dsAttrTypeStandard:CACertificate"

"""
 kDS1AttrCapabilities
 Used with directory nodes so that clients can "discover" the
 API capabilities for this Directory Node.
"""
kDS1AttrCapabilities = "dsAttrTypeStandard:Capabilities"

"""
 kDS1AttrCapacity
 Attribute type for the capacity of a resource.
     found in resource records (kDSStdRecordTypeResources).
    Example: 50
"""
kDS1AttrCapacity = "dsAttrTypeStandard:Capacity"

"""
    kDS1AttrCategory
    The category of an item used for browsing
"""
kDS1AttrCategory = "dsAttrTypeStandard:Category"

"""
 kDS1AttrCertificateRevocationList
 Attribute containing the binary of the certificate revocation list.
 This is a list of certificates which are no longer trusted.
 Usually found in kDSStdRecordTypeCertificateAuthority records.
"""
kDS1AttrCertificateRevocationList = "dsAttrTypeStandard:CertificateRevocationList"

"""
 kDS1AttrChange
 Retained for backward compatibility.
"""
kDS1AttrChange = "dsAttrTypeStandard:Change"

"""
 kDS1AttrComment
 Attribute used for unformatted comment.
"""
kDS1AttrComment = "dsAttrTypeStandard:Comment"

"""
 kDS1AttrContactGUID
 Attribute type for the contact GUID of a group.
     found in group records (kDSStdRecordTypeGroups).
"""
kDS1AttrContactGUID = "dsAttrTypeStandard:ContactGUID"

"""
 kDS1AttrContactPerson
 Attribute type for the contact person of the machine.
        Found in host or machine records.
"""
kDS1AttrContactPerson = "dsAttrTypeStandard:ContactPerson"

"""
 kDS1AttrCreationTimestamp
 Attribute showing date/time of record creation.
 Format is x.208 standard YYYYMMDDHHMMSSZ which we will require as GMT time.
"""
kDS1AttrCreationTimestamp = "dsAttrTypeStandard:CreationTimestamp"

"""
 kDS1AttrCrossCertificatePair
 Attribute containing the binary of a pair of certificates which
 verify each other.  Both certificates have the same level of authority.
 Usually found in kDSStdRecordTypeCertificateAuthority records.
"""
kDS1AttrCrossCertificatePair = "dsAttrTypeStandard:CrossCertificatePair"

"""
 kDS1AttrDataStamp
 checksum/meta data
"""
kDS1AttrDataStamp = "dsAttrTypeStandard:DataStamp"

"""
 kDS1AttrDistinguishedName
 Users distinguished or real name
"""
kDS1AttrDistinguishedName = "dsAttrTypeStandard:RealName"

"""
 kDS1AttrDNSDomain
 DNS Resolver domain attribute.
"""
kDS1AttrDNSDomain = "dsAttrTypeStandard:DNSDomain"

"""
 kDS1AttrDNSNameServer
 DNS Resolver nameserver attribute.
"""
kDS1AttrDNSNameServer = "dsAttrTypeStandard:DNSNameServer"

"""
 kDS1AttrENetAddress
 Single-valued attribute for hardware Ethernet address (MAC address).
        Found in machine records (kDSStdRecordTypeMachines) and computer records
        (kDSStdRecordTypeComputers).
"""
kDS1AttrENetAddress = "dsAttrTypeStandard:ENetAddress"

"""
 kDS1AttrExpire
 Used for expiration date or time depending on association.
"""
kDS1AttrExpire = "dsAttrTypeStandard:Expire"

"""
 kDS1AttrFirstName
 Used for first name of user or person record.
"""
kDS1AttrFirstName = "dsAttrTypeStandard:FirstName"

"""
 kDS1AttrGeneratedUID
 Used for 36 character (128 bit) unique ID. Usually found in user,
 group, and computer records. An example value is "A579E95E-CDFE-4EBC-B7E7-F2158562170F".
 The standard format contains 32 hex characters and four hyphen characters.
"""
kDS1AttrGeneratedUID = "dsAttrTypeStandard:GeneratedUID"

"""
    kDS1AttrHomeDirectoryQuota
    Represents the allowed usage for a user's home directory in bytes.
        Found in user records (kDSStdRecordTypeUsers).
"""
kDS1AttrHomeDirectoryQuota = "dsAttrTypeStandard:HomeDirectoryQuota"

"""
 kDS1AttrHomeDirectorySoftQuota
 Used to define home directory size limit in bytes when user is notified
 that the hard limit is approaching.
"""
kDS1AttrHomeDirectorySoftQuota = "dsAttrTypeStandard:HomeDirectorySoftQuota"

"""
    kDS1AttrHomeLocOwner
    Represents the owner of a workgroup's shared home directory.
        Typically found in kDSStdRecordTypeGroups records.
"""
kDS1AttrHomeLocOwner = "dsAttrTypeStandard:HomeLocOwner"

"""
    kDS1StandardAttrHomeLocOwner
    Retained for backward compatibility.
"""
kDS1StandardAttrHomeLocOwner = kDS1AttrHomeLocOwner

"""
 kDS1AttrInternetAlias
 Used to track internet alias.
"""
kDS1AttrInternetAlias = "dsAttrTypeStandard:InetAlias"

"""
 kDS1AttrKDCConfigData
 Contents of the kdc.conf file.
"""
kDS1AttrKDCConfigData = "dsAttrTypeStandard:KDCConfigData"

"""
 kDS1AttrLastName
 Used for the last name of user or person record.
"""
kDS1AttrLastName = "dsAttrTypeStandard:LastName"

"""
 kDS1AttrLDAPSearchBaseSuffix
 Search base suffix for a LDAP server.
"""
kDS1AttrLDAPSearchBaseSuffix = "dsAttrTypeStandard:LDAPSearchBaseSuffix"

"""
 kDS1AttrLocation
 Represents the location a service is available from (usually domain name).
     Typically found in service record types including kDSStdRecordTypeAFPServer,
     kDSStdRecordTypeLDAPServer, and kDSStdRecordTypeWebServer.
"""
kDS1AttrLocation = "dsAttrTypeStandard:Location"

"""
 kDS1AttrMapGUID
 Represents the GUID for a record's map.
"""
kDS1AttrMapGUID = "dsAttrTypeStandard:MapGUID"

"""
 kDS1AttrMCXFlags
 Used by MCX.
"""
kDS1AttrMCXFlags = "dsAttrTypeStandard:MCXFlags"

"""
 kDS1AttrMCXSettings
 Used by MCX.
"""
kDS1AttrMCXSettings = "dsAttrTypeStandard:MCXSettings"

"""
 kDS1AttrMailAttribute
 Holds the mail account config data.
"""
kDS1AttrMailAttribute = "dsAttrTypeStandard:MailAttribute"

"""
 kDS1AttrMetaAutomountMap
 Used to query for kDSStdRecordTypeAutomount entries associated with a specific
 kDSStdRecordTypeAutomountMap.
"""
kDS1AttrMetaAutomountMap = "dsAttrTypeStandard:MetaAutomountMap"

"""
 kDS1AttrMiddleName
 Used for the middle name of user or person record.
"""
kDS1AttrMiddleName = "dsAttrTypeStandard:MiddleName"

"""
 kDS1AttrModificationTimestamp
 Attribute showing date/time of record modification.
 Format is x.208 standard YYYYMMDDHHMMSSZ which we will require as GMT time.
"""
kDS1AttrModificationTimestamp = "dsAttrTypeStandard:ModificationTimestamp"

"""
 kDSNAttrNeighborhoodAlias
 Attribute type in Neighborhood records describing sub-neighborhood records.
"""
kDSNAttrNeighborhoodAlias = "dsAttrTypeStandard:NeighborhoodAlias"

"""
 kDS1AttrNeighborhoodType
 Attribute type in Neighborhood records describing their function.
"""
kDS1AttrNeighborhoodType = "dsAttrTypeStandard:NeighborhoodType"

"""
 kDS1AttrNetworkView
 The name of the managed network view a computer should use for browsing.
"""
kDS1AttrNetworkView = "dsAttrTypeStandard:NetworkView"

"""
 kDS1AttrNFSHomeDirectory
 Defines a user's home directory mount point on the local machine.
"""
kDS1AttrNFSHomeDirectory = "dsAttrTypeStandard:NFSHomeDirectory"

"""
 kDS1AttrNote
 Note attribute. Commonly used in printer records.
"""
kDS1AttrNote = "dsAttrTypeStandard:Note"

"""
 kDS1AttrOwner
 Attribute type for the owner of a record.
        Typically the value is a LDAP distinguished name.
"""
kDS1AttrOwner = "dsAttrTypeStandard:Owner"

"""
 kDS1AttrOwnerGUID
 Attribute type for the owner GUID of a group.
     found in group records (kDSStdRecordTypeGroups).
"""
kDS1AttrOwnerGUID = "dsAttrTypeStandard:OwnerGUID"

"""
 kDS1AttrPassword
 Holds the password or credential value.
"""
kDS1AttrPassword = "dsAttrTypeStandard:Password"

"""
 kDS1AttrPasswordPlus
 Holds marker data to indicate possible authentication redirection.
"""
kDS1AttrPasswordPlus = "dsAttrTypeStandard:PasswordPlus"

"""
 kDS1AttrPasswordPolicyOptions
 Collection of password policy options in single attribute.
 Used in user presets record.
"""
kDS1AttrPasswordPolicyOptions = "dsAttrTypeStandard:PasswordPolicyOptions"

"""
 kDS1AttrPasswordServerList
 Represents the attribute for storing the password server's replication information.
"""
kDS1AttrPasswordServerList = "dsAttrTypeStandard:PasswordServerList"

"""
    kDS1AttrPasswordServerLocation
    Specifies the IP address or domain name of the Password Server associated
        with a given directory node. Found in a config record named PasswordServer.
"""
kDS1AttrPasswordServerLocation = "dsAttrTypeStandard:PasswordServerLocation"

"""
 kDS1AttrPicture
 Represents the path of the picture for each user displayed in the login window.
 Found in user records (kDSStdRecordTypeUsers).
"""
kDS1AttrPicture = "dsAttrTypeStandard:Picture"

"""
 kDS1AttrPort
 Represents the port number a service is available on.
     Typically found in service record types including kDSStdRecordTypeAFPServer,
     kDSStdRecordTypeLDAPServer, and kDSStdRecordTypeWebServer.
"""
kDS1AttrPort = "dsAttrTypeStandard:Port"

"""
    kDS1AttrPresetUserIsAdmin
    Flag to indicate whether users created from this preset are administrators
        by default. Found in kDSStdRecordTypePresetUsers records.
"""
kDS1AttrPresetUserIsAdmin = "dsAttrTypeStandard:PresetUserIsAdmin"

"""
 kDS1AttrPrimaryComputerGUID
 Single-valued attribute that defines a primary computer of the computer group.
 added via extensible object for computer group record type (kDSStdRecordTypeComputerGroups)
"""
kDS1AttrPrimaryComputerGUID = "dsAttrTypeStandard:PrimaryComputerGUID"

"""
 kDS1AttrPrimaryComputerList
 The GUID of the computer list with which this computer record is associated.
"""
kDS1AttrPrimaryComputerList = "dsAttrTypeStandard:PrimaryComputerList"

"""
 kDS1AttrPrimaryGroupID
 This is the 32 bit unique ID that represents the primary group
 a user is part of, or the ID of a group. Format is a signed 32 bit integer
 represented as a string.
"""
kDS1AttrPrimaryGroupID = "dsAttrTypeStandard:PrimaryGroupID"

"""
 kDS1AttrPrinter1284DeviceID
 Single-valued attribute that defines the IEEE 1284 DeviceID of a printer.
              This is used when configuring a printer.
"""
kDS1AttrPrinter1284DeviceID = "dsAttrTypeStandard:Printer1284DeviceID"

"""
 kDS1AttrPrinterLPRHost
 Standard attribute type for kDSStdRecordTypePrinters.
"""
kDS1AttrPrinterLPRHost = "dsAttrTypeStandard:PrinterLPRHost"

"""
 kDS1AttrPrinterLPRQueue
 Standard attribute type for kDSStdRecordTypePrinters.
"""
kDS1AttrPrinterLPRQueue = "dsAttrTypeStandard:PrinterLPRQueue"

"""
 kDS1AttrPrinterMakeAndModel
 Single-valued attribute for definition of the Printer Make and Model.  An example
              Value would be "HP LaserJet 2200".  This would be used to determine the proper PPD
              file to be used when configuring a printer from the Directory.  This attribute
              is based on the IPP Printing Specification RFC and IETF IPP-LDAP Printer Record.
"""
kDS1AttrPrinterMakeAndModel = "dsAttrTypeStandard:PrinterMakeAndModel"

"""
 kDS1AttrPrinterType
 Standard attribute type for kDSStdRecordTypePrinters.
"""
kDS1AttrPrinterType = "dsAttrTypeStandard:PrinterType"

"""
 kDS1AttrPrinterURI
 Single-valued attribute that defines the URI of a printer "ipp://address" or
              "smb://server/queue".  This is used when configuring a printer. This attribute
                is based on the IPP Printing Specification RFC and IETF IPP-LDAP Printer Record.
"""
kDS1AttrPrinterURI = "dsAttrTypeStandard:PrinterURI"

"""
 kDS1AttrPrinterXRISupported
 Multi-valued attribute that defines additional URIs supported by a printer.
              This is used when configuring a printer. This attribute is based on the IPP
                Printing Specification RFC and IETF IPP-LDAP Printer Record.
"""
kDSNAttrPrinterXRISupported = "dsAttrTypeStandard:PrinterXRISupported"

"""
 kDS1AttrPrintServiceInfoText
 Standard attribute type for kDSStdRecordTypePrinters.
"""
kDS1AttrPrintServiceInfoText = "dsAttrTypeStandard:PrintServiceInfoText"

"""
 kDS1AttrPrintServiceInfoXML
 Standard attribute type for kDSStdRecordTypePrinters.
"""
kDS1AttrPrintServiceInfoXML = "dsAttrTypeStandard:PrintServiceInfoXML"

"""
 kDS1AttrPrintServiceUserData
 Single-valued attribute for print quota configuration or statistics
        (XML data). Found in user records (kDSStdRecordTypeUsers) or print service
        statistics records (kDSStdRecordTypePrintServiceUser).
"""
kDS1AttrPrintServiceUserData = "dsAttrTypeStandard:PrintServiceUserData"

"""
 kDS1AttrRealUserID
 Used by MCX.
"""
kDS1AttrRealUserID = "dsAttrTypeStandard:RealUserID"

"""
 kDS1AttrRelativeDNPrefix
 Used to map the first native LDAP attribute type required in the building of the
  Relative Distinguished Name for LDAP record creation.
"""
kDS1AttrRelativeDNPrefix = "dsAttrTypeStandard:RelativeDNPrefix"

"""
 kDS1AttrSMBAcctFlags
 Account control flag.
"""
kDS1AttrSMBAcctFlags = "dsAttrTypeStandard:SMBAccountFlags"

"""
 kDS1AttrSMBGroupRID
 Constant for supporting PDC SMB interaction with DS.
"""
kDS1AttrSMBGroupRID = "dsAttrTypeStandard:SMBGroupRID"

"""
 kDS1AttrSMBHome

     UNC address of Windows homedirectory mount point (\\server\\sharepoint).
"""
kDS1AttrSMBHome = "dsAttrTypeStandard:SMBHome"

"""
 kDS1AttrSMBHomeDrive

     Drive letter for homedirectory mount point.
"""
kDS1AttrSMBHomeDrive = "dsAttrTypeStandard:SMBHomeDrive"

"""
 kDS1AttrSMBKickoffTime
 Attribute in support of SMB interaction.
"""
kDS1AttrSMBKickoffTime = "dsAttrTypeStandard:SMBKickoffTime"

"""
 kDS1AttrSMBLogoffTime
 Attribute in support of SMB interaction.
"""
kDS1AttrSMBLogoffTime = "dsAttrTypeStandard:SMBLogoffTime"

"""
 kDS1AttrSMBLogonTime
 Attribute in support of SMB interaction.
"""
kDS1AttrSMBLogonTime = "dsAttrTypeStandard:SMBLogonTime"

"""
 kDS1AttrSMBPrimaryGroupSID
 SMB Primary Group Security ID, stored as a string attribute of
    up to 64 bytes. Found in user, group, and computer records
    (kDSStdRecordTypeUsers, kDSStdRecordTypeGroups, kDSStdRecordTypeComputers).
"""
kDS1AttrSMBPrimaryGroupSID = "dsAttrTypeStandard:SMBPrimaryGroupSID"

"""
 kDS1AttrSMBPWDLastSet
 Attribute in support of SMB interaction.
"""
kDS1AttrSMBPWDLastSet = "dsAttrTypeStandard:SMBPasswordLastSet"

"""
 kDS1AttrSMBProfilePath
 Desktop management info (dock, desktop links, etc).
"""
kDS1AttrSMBProfilePath = "dsAttrTypeStandard:SMBProfilePath"

"""
 kDS1AttrSMBRID
 Attribute in support of SMB interaction.
"""
kDS1AttrSMBRID = "dsAttrTypeStandard:SMBRID"

"""
 kDS1AttrSMBScriptPath
 Login script path.
"""
kDS1AttrSMBScriptPath = "dsAttrTypeStandard:SMBScriptPath"

"""
 kDS1AttrSMBSID
 SMB Security ID, stored as a string attribute of up to 64 bytes.
    Found in user, group, and computer records (kDSStdRecordTypeUsers,
    kDSStdRecordTypeGroups, kDSStdRecordTypeComputers).
"""
kDS1AttrSMBSID = "dsAttrTypeStandard:SMBSID"

"""
 kDS1AttrSMBUserWorkstations
 List of workstations user can login from (machine account names).
"""
kDS1AttrSMBUserWorkstations = "dsAttrTypeStandard:SMBUserWorkstations"

"""
 kDS1AttrServiceType
 Represents the service type for the service.  This is the raw service type of the
     service.  For example a service record type of kDSStdRecordTypeWebServer
     might have a service type of "http" or "https".
"""
kDS1AttrServiceType = "dsAttrTypeStandard:ServiceType"

"""
 kDS1AttrSetupAdvertising
 Used for Setup Assistant automatic population.
"""
kDS1AttrSetupAdvertising = "dsAttrTypeStandard:SetupAssistantAdvertising"

"""
 kDS1AttrSetupAutoRegister
 Used for Setup Assistant automatic population.
"""
kDS1AttrSetupAutoRegister = "dsAttrTypeStandard:SetupAssistantAutoRegister"

"""
 kDS1AttrSetupLocation
 Used for Setup Assistant automatic population.
"""
kDS1AttrSetupLocation = "dsAttrTypeStandard:SetupAssistantLocation"

"""
 kDS1AttrSetupOccupation
 Used for Setup Assistant automatic population.
"""
kDS1AttrSetupOccupation = "dsAttrTypeStandard:Occupation"

"""
 kDS1AttrTimeToLive
 Attribute recommending how long to cache the record's attribute values.
 Format is an unsigned 32 bit representing seconds. i.e. 300 is 5 minutes.
"""
kDS1AttrTimeToLive = "dsAttrTypeStandard:TimeToLive"

"""
 kDS1AttrUniqueID
 This is the 32 bit unique ID that represents the user in the legacy manner.
 Format is a signed integer represented as a string.
"""
kDS1AttrUniqueID = "dsAttrTypeStandard:UniqueID"

"""
 kDS1AttrUserCertificate
 Attribute containing the binary of the user's certificate.
 Usually found in user records. The certificate is data which identifies a user.
 This data is attested to by a known party, and can be independently verified
 by a third party.
"""
kDS1AttrUserCertificate = "dsAttrTypeStandard:UserCertificate"

"""
 kDS1AttrUserPKCS12Data
 Attribute containing binary data in PKCS #12 format.
 Usually found in user records. The value can contain keys, certificates,
 and other related information and is encrypted with a passphrase.
"""
kDS1AttrUserPKCS12Data = "dsAttrTypeStandard:UserPKCS12Data"

"""
 kDS1AttrUserShell
 Used to represent the user's shell setting.
"""
kDS1AttrUserShell = "dsAttrTypeStandard:UserShell"

"""
 kDS1AttrUserSMIMECertificate
 Attribute containing the binary of the user's SMIME certificate.
 Usually found in user records. The certificate is data which identifies a user.
 This data is attested to by a known party, and can be independently verified
 by a third party. SMIME certificates are often used for signed or encrypted
 emails.
"""
kDS1AttrUserSMIMECertificate = "dsAttrTypeStandard:UserSMIMECertificate"

"""
 kDS1AttrVFSDumpFreq
 Attribute used to support mount records.
"""
kDS1AttrVFSDumpFreq = "dsAttrTypeStandard:VFSDumpFreq"

"""
 kDS1AttrVFSLinkDir
 Attribute used to support mount records.
"""
kDS1AttrVFSLinkDir = "dsAttrTypeStandard:VFSLinkDir"

"""
 kDS1AttrVFSPassNo
 Attribute used to support mount records.
"""
kDS1AttrVFSPassNo = "dsAttrTypeStandard:VFSPassNo"

"""
 kDS1AttrVFSType
 Attribute used to support mount records.
"""
kDS1AttrVFSType = "dsAttrTypeStandard:VFSType"

"""
 kDS1AttrWeblogURI
 Single-valued attribute that defines the URI of a user's weblog.
    Usually found in user records (kDSStdRecordTypeUsers).
    Example: http://example.com/blog/jsmith
"""
kDS1AttrWeblogURI = "dsAttrTypeStandard:WeblogURI"

"""
    kDS1AttrXMLPlist
    SA config settings plist.
"""
kDS1AttrXMLPlist = "dsAttrTypeStandard:XMLPlist"

"""
 kDS1AttrProtocolNumber
 Single-valued attribute that defines a protocol number.  Usually found
  in protocol records (kDSStdRecordTypeProtocols)
"""
kDS1AttrProtocolNumber = "dsAttrTypeStandard:ProtocolNumber"

"""
 kDS1AttrRPCNumber
 Single-valued attribute that defines an RPC number.  Usually found
  in RPC records (kDSStdRecordTypeRPC)
"""
kDS1AttrRPCNumber = "dsAttrTypeStandard:RPCNumber"

"""
 kDS1AttrNetworkNumber
 Single-valued attribute that defines a network number.  Usually found
  in network records (kDSStdRecordTypeNetworks)
"""
kDS1AttrNetworkNumber = "dsAttrTypeStandard:NetworkNumber"


# Multiple Valued Specific Attribute Type Constants


"""
 DirectoryService Multiple Valued Specific Attribute Type Constants
"""

"""
 kDSNAttrAccessControlEntry
 Attribute type which stores directory access control directives.
"""
kDSNAttrAccessControlEntry = "dsAttrTypeStandard:AccessControlEntry"

"""
 kDSNAttrAddressLine1
 Line one of multiple lines of address data for a user.
"""
kDSNAttrAddressLine1 = "dsAttrTypeStandard:AddressLine1"

"""
 kDSNAttrAddressLine2
 Line two of multiple lines of address data for a user.
"""
kDSNAttrAddressLine2 = "dsAttrTypeStandard:AddressLine2"

"""
 kDSNAttrAddressLine3
 Line three of multiple lines of address data for a user.
"""
kDSNAttrAddressLine3 = "dsAttrTypeStandard:AddressLine3"

"""
 kDSNAttrAltSecurityIdentities
 Alternative Security Identities such as Kerberos principals.
"""
kDSNAttrAltSecurityIdentities = "dsAttrTypeStandard:AltSecurityIdentities"

"""
 kDSNAttrAreaCode
 Area code of a user's phone number.
"""
kDSNAttrAreaCode = "dsAttrTypeStandard:AreaCode"

"""
 kDSNAttrAuthenticationAuthority
 Determines what mechanism is used to verify or set a user's password.
     If multiple values are present, the first attributes returned take precedence.
     Typically found in User records (kDSStdRecordTypeUsers).
"""
kDSNAttrAuthenticationAuthority = "dsAttrTypeStandard:AuthenticationAuthority"

"""
 kDSNAttrAutomountInformation
 Used to store automount information in kDSStdRecordTypeAutomount records.
"""
kDSNAttrAutomountInformation = "dsAttrTypeStandard:AutomountInformation"

"""
 kDSNAttrBootParams
 Attribute type in host or machine records for storing boot params.
"""
kDSNAttrBootParams = "dsAttrTypeStandard:BootParams"

"""
 kDSNAttrBuilding
 Represents the building name for a user or person record.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrBuilding = "dsAttrTypeStandard:Building"

"""
 kDSNAttrCalendarPrincipalURI
 the URI for a record's calendar
"""
kDSNAttrCalendarPrincipalURI = "dsAttrTypeStandard:CalendarPrincipalURI"

"""
 kDSNAttrCity
 Usually, city for a user or person record.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrCity = "dsAttrTypeStandard:City"

"""
 kDSNAttrCompany
 attribute that defines the user's company.
 Example: Apple Computer, Inc
"""
kDSNAttrCompany = "dsAttrTypeStandard:Company"

"""
 kDSNAttrComputerAlias
 Attribute type in Neighborhood records describing computer records pointed to by
 this neighborhood.
"""
kDSNAttrComputerAlias = "dsAttrTypeStandard:ComputerAlias"

"""
 kDSNAttrComputers
 List of computers.
"""
kDSNAttrComputers = "dsAttrTypeStandard:Computers"

"""
 kDSNAttrCountry
 Represents country of a record entry.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrCountry = "dsAttrTypeStandard:Country"

"""
 kDSNAttrDepartment
 Represents the department name of a user or person.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrDepartment = "dsAttrTypeStandard:Department"

"""
 kDSNAttrDNSName
 Domain Name Service name.
"""
kDSNAttrDNSName = "dsAttrTypeStandard:DNSName"

"""
 kDSNAttrEMailAddress
 Email address of usually a user record.
"""
kDSNAttrEMailAddress = "dsAttrTypeStandard:EMailAddress"

"""
 kDSNAttrEMailContacts
 multi-valued attribute that defines a record's custom email addresses .
     found in user records (kDSStdRecordTypeUsers).
    Example: home:johndoe@mymail.com
"""
kDSNAttrEMailContacts = "dsAttrTypeStandard:EMailContacts"

"""
 kDSNAttrFaxNumber
 Represents the FAX numbers of a user or person.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrFaxNumber = "dsAttrTypeStandard:FAXNumber"

"""
 kDSNAttrGroup
 List of groups.
"""
kDSNAttrGroup = "dsAttrTypeStandard:Group"

"""
 kDSNAttrGroupMembers
 Attribute type in group records containing lists of GUID values for members other than groups.
"""
kDSNAttrGroupMembers = "dsAttrTypeStandard:GroupMembers"

"""
 kDSNAttrGroupMembership
 Usually a list of users that below to a given group record.
"""
kDSNAttrGroupMembership = "dsAttrTypeStandard:GroupMembership"

"""
 kDSNAttrGroupServices
 xml-plist attribute that defines a group's services .
     found in group records (kDSStdRecordTypeGroups).
"""
kDSNAttrGroupServices = "dsAttrTypeStandard:GroupServices"

"""
 kDSNAttrHomePhoneNumber
 Home telephone number of a user or person.
"""
kDSNAttrHomePhoneNumber = "dsAttrTypeStandard:HomePhoneNumber"

"""
 kDSNAttrHTML
 HTML location.
"""
kDSNAttrHTML = "dsAttrTypeStandard:HTML"

"""
 kDSNAttrHomeDirectory
 Network home directory URL.
"""
kDSNAttrHomeDirectory = "dsAttrTypeStandard:HomeDirectory"

"""
 kDSNAttrIMHandle
 Represents the Instant Messaging handles of a user.
 Values should be prefixed with the appropriate IM type
 ie. AIM:, Jabber:, MSN:, Yahoo:, or ICQ:
 Usually found in user records (kDSStdRecordTypeUsers).
"""
kDSNAttrIMHandle = "dsAttrTypeStandard:IMHandle"

"""
 kDSNAttrIPAddress
 IP address expressed either as domain or IP notation.
"""
kDSNAttrIPAddress = "dsAttrTypeStandard:IPAddress"

"""
    kDSNAttrIPAddressAndENetAddress
 A pairing of IPv4 or IPv6 addresses with Ethernet addresses
 (e.g., "10.1.1.1/00:16:cb:92:56:41").  Usually found on kDSStdRecordTypeComputers for use by
 services that need specific pairing of the two values.  This should be in addition to
 kDSNAttrIPAddress, kDSNAttrIPv6Address and kDS1AttrENetAddress. This is necessary because not
 all directories return attribute values in a guaranteed order.
"""
kDSNAttrIPAddressAndENetAddress = "dsAttrTypeStandard:IPAddressAndENetAddress"

"""
 kDSNAttrIPv6Address
 IPv6 address expressed in the standard notation (e.g., "fe80::236:caff:fcc2:5641" )
 Usually found on kDSStdRecordTypeComputers, kDSStdRecordTypeHosts, and
 kDSStdRecordTypeMachines.
"""
kDSNAttrIPv6Address = "dsAttrTypeStandard:IPv6Address"

"""
 kDSNAttrJPEGPhoto
 Used to store binary picture data in JPEG format.
 Usually found in user, people or group records (kDSStdRecordTypeUsers,
 kDSStdRecordTypePeople, kDSStdRecordTypeGroups).
"""
kDSNAttrJPEGPhoto = "dsAttrTypeStandard:JPEGPhoto"

"""
 kDSNAttrJobTitle
 Represents the job title of a user.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrJobTitle = "dsAttrTypeStandard:JobTitle"

"""
 kDSNAttrKDCAuthKey
 KDC master key RSA encrypted with realm public key.
"""
kDSNAttrKDCAuthKey = "dsAttrTypeStandard:KDCAuthKey"

"""
    kDSNAttrKeywords
    Keywords using for searching capability.
"""
kDSNAttrKeywords = "dsAttrTypeStandard:Keywords"

"""
 kDSNAttrLDAPReadReplicas
 List of LDAP server URLs which can each be used to read directory data.
"""
kDSNAttrLDAPReadReplicas = "dsAttrTypeStandard:LDAPReadReplicas"

"""
 kDSNAttrLDAPWriteReplicas
 List of LDAP server URLs which can each be used to write directory data.
"""
kDSNAttrLDAPWriteReplicas = "dsAttrTypeStandard:LDAPWriteReplicas"

"""
 kDSNAttrMachineServes
 Attribute type in host or machine records for storing NetInfo
        domains served.
"""
kDSNAttrMachineServes = "dsAttrTypeStandard:MachineServes"

"""
 kDSNAttrMapCoordinates
 attribute that defines coordinates for a user's location .
*     found in user records (kDSStdRecordTypeUsers) and resource records (kDSStdRecordTypeResources).
    Example: 7.7,10.6
"""
kDSNAttrMapCoordinates = "dsAttrTypeStandard:MapCoordinates"

"""
 kDSNAttrMapURI
 attribute that defines the URI of a user's location.
    Usually found in user records (kDSStdRecordTypeUsers).
    Example: http://example.com/bldg1
"""
kDSNAttrMapURI = "dsAttrTypeStandard:MapURI"

"""
 kDSNAttrMCXSettings
 Used by MCX.
"""
kDSNAttrMCXSettings = "dsAttrTypeStandard:MCXSettings"

"""
 kDSNAttrMIME
 Data contained in this attribute type is a fully qualified MIME Type.
"""
kDSNAttrMIME = "dsAttrTypeStandard:MIME"

"""
 kDSNAttrMember
 List of member records.
"""
kDSNAttrMember = "dsAttrTypeStandard:Member"

"""
 kDSNAttrMobileNumber
 Represents the mobile numbers of a user or person.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrMobileNumber = "dsAttrTypeStandard:MobileNumber"

"""
 kDSNAttrNBPEntry
 Appletalk data.
"""
kDSNAttrNBPEntry = "dsAttrTypeStandard:NBPEntry"

"""
 kDSNAttrNestedGroups
 Attribute type in group records for the list of GUID values for nested groups.
"""
kDSNAttrNestedGroups = "dsAttrTypeStandard:NestedGroups"

"""
 kDSNAttrNetGroups
 Attribute type that indicates which netgroups its record is a member of.
        Found in user, host, and netdomain records.
"""
kDSNAttrNetGroups = "dsAttrTypeStandard:NetGroups"

"""
 kDSNAttrNickName
 Represents the nickname of a user or person.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrNickName = "dsAttrTypeStandard:NickName"

"""
 kDSNAttrNodePathXMLPlist
 Attribute type in Neighborhood records describing the DS Node to search while
 looking up aliases in this neighborhood.
"""
kDSNAttrNodePathXMLPlist = "dsAttrTypeStandard:NodePathXMLPlist"

"""
 kDSNAttrOrganizationInfo
 Usually the organization info of a user.
"""
kDSNAttrOrganizationInfo = "dsAttrTypeStandard:OrganizationInfo"

"""
 kDSNAttrOrganizationName
 Usually the organization of a user.
"""
kDSNAttrOrganizationName = "dsAttrTypeStandard:OrganizationName"

"""
 kDSNAttrPagerNumber
 Represents the pager numbers of a user or person.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrPagerNumber = "dsAttrTypeStandard:PagerNumber"

"""
 kDSNAttrPhoneContacts
 multi-valued attribute that defines a record's custom phone numbers .
     found in user records (kDSStdRecordTypeUsers).
    Example: home fax:408-555-4444
"""
kDSNAttrPhoneContacts = "dsAttrTypeStandard:PhoneContacts"


"""
 kDSNAttrPhoneNumber
 Telephone number of a user.
"""
kDSNAttrPhoneNumber = "dsAttrTypeStandard:PhoneNumber"

"""
 kDSNAttrPGPPublicKey
 Pretty Good Privacy public encryption key.
"""
kDSNAttrPGPPublicKey = "dsAttrTypeStandard:PGPPublicKey"

"""
 kDSNAttrPostalAddress
 The postal address usually excluding postal code.
"""
kDSNAttrPostalAddress = "dsAttrTypeStandard:PostalAddress"

"""
* kDSNAttrPostalAddressContacts
* multi-valued attribute that defines a record's alternate postal addresses .
*     found in user records (kDSStdRecordTypeUsers) and resource records (kDSStdRecordTypeResources).
"""
kDSNAttrPostalAddressContacts = "dsAttrTypeStandard:PostalAddressContacts"

"""
 kDSNAttrPostalCode
 The postal code such as zip code in the USA.
"""
kDSNAttrPostalCode = "dsAttrTypeStandard:PostalCode"

"""
 kDSNAttrNamePrefix
 Represents the title prefix of a user or person.
 ie. Mr., Ms., Mrs., Dr., etc.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrNamePrefix = "dsAttrTypeStandard:NamePrefix"

"""
 kDSNAttrProtocols
 List of protocols.
"""
kDSNAttrProtocols = "dsAttrTypeStandard:Protocols"

"""
 kDSNAttrRecordName
 List of names/keys for this record.
"""
kDSNAttrRecordName = "dsAttrTypeStandard:RecordName"

"""
 kDSNAttrRelationships
 multi-valued attribute that defines the relationship to the record type .
     found in user records (kDSStdRecordTypeUsers).
    Example: brother:John
"""
kDSNAttrRelationships = "dsAttrTypeStandard:Relationships"

"""
* kDSNAttrResourceInfo
* multi-valued attribute that defines a resource record's info.
"""
kDSNAttrResourceInfo = "dsAttrTypeStandard:ResourceInfo"

"""
 kDSNAttrResourceType
 Attribute type for the kind of resource.
     found in resource records (kDSStdRecordTypeResources).
    Example: ConferenceRoom
"""
kDSNAttrResourceType = "dsAttrTypeStandard:ResourceType"

"""
 kDSNAttrServicesLocator
 Attribute describing the services hosted for the record.
"""
kDSNAttrServicesLocator = "dsAttrTypeStandard:ServicesLocator"

"""
 kDSNAttrState
 The state or province of a country.
"""
kDSNAttrState = "dsAttrTypeStandard:State"

"""
 kDSNAttrStreet
 Represents the street address of a user or person.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrStreet = "dsAttrTypeStandard:Street"

"""
 kDSNAttrNameSuffix
 Represents the name suffix of a user or person.
 ie. Jr., Sr., etc.
 Usually found in user or people records (kDSStdRecordTypeUsers or
 kDSStdRecordTypePeople).
"""
kDSNAttrNameSuffix = "dsAttrTypeStandard:NameSuffix"

"""
 kDSNAttrURL
 List of URLs.
"""
kDSNAttrURL = "dsAttrTypeStandard:URL"

"""
 kDSNAttrURLForNSL
 List of URLs used by NSL.
"""
kDSNAttrURLForNSL = "dsAttrTypeStandard:URLForNSL"

"""
 kDSNAttrVFSOpts
 Used in support of mount records.
"""
kDSNAttrVFSOpts = "dsAttrTypeStandard:VFSOpts"



# Other Attribute Type Constants


"""
 DirectoryService Other Attribute Type Constants Not Mapped by Directory Node Plugins
 Mainly used internally by the DirectoryService Daemon or made available via dsGetDirNodeInfo()
"""

"""
 kDS1AttrAdminStatus
 Retained only for backward compatibility.
"""
kDS1AttrAdminStatus = "dsAttrTypeStandard:AdminStatus"

"""
 kDS1AttrAlias
 Alias attribute, contain pointer to another node/record/attribute.
"""
kDS1AttrAlias = "dsAttrTypeStandard:Alias"

"""
 kDS1AttrAuthCredential
 An "auth" credential, to be used to authenticate to other Directory nodes.
"""
kDS1AttrAuthCredential = "dsAttrTypeStandard:AuthCredential"

"""
 kDS1AttrCopyTimestamp
 Timestamp used in local account caching.
"""
kDS1AttrCopyTimestamp = "dsAttrTypeStandard:CopyTimestamp"

"""
    kDS1AttrDateRecordCreated
    Date of record creation.
"""
kDS1AttrDateRecordCreated = "dsAttrTypeStandard:DateRecordCreated"

"""
 kDS1AttrKerberosRealm
 Supports Kerberized SMB Server services.
"""
kDS1AttrKerberosRealm = "dsAttrTypeStandard:KerberosRealm"

"""
 kDS1AttrNTDomainComputerAccount
 Supports Kerberized SMB Server services.
"""
kDS1AttrNTDomainComputerAccount = "dsAttrTypeStandard:NTDomainComputerAccount"

"""
 kDSNAttrOriginalHomeDirectory
 Home directory URL used in local account caching.
"""
kDSNAttrOriginalHomeDirectory = "dsAttrTypeStandard:OriginalHomeDirectory"

"""
 kDS1AttrOriginalNFSHomeDirectory
 NFS home directory used in local account caching.
"""
kDS1AttrOriginalNFSHomeDirectory = "dsAttrTypeStandard:OriginalNFSHomeDirectory"

"""
 kDS1AttrOriginalNodeName
 Nodename used in local account caching.
"""
kDS1AttrOriginalNodeName = "dsAttrTypeStandard:OriginalNodeName"

"""
 kDS1AttrPrimaryNTDomain
 Supports Kerberized SMB Server services.
"""
kDS1AttrPrimaryNTDomain = "dsAttrTypeStandard:PrimaryNTDomain"

"""
 kDS1AttrPwdAgingPolicy
 Contains the password aging policy data for an authentication capable record.
"""
kDS1AttrPwdAgingPolicy = "dsAttrTypeStandard:PwdAgingPolicy"

"""
 kDS1AttrRARA
 Retained only for backward compatibility.
"""
kDS1AttrRARA = "dsAttrTypeStandard:RARA"

"""
 kDS1AttrReadOnlyNode
 Can be found using dsGetDirNodeInfo and will return one of
 ReadOnly, ReadWrite, or WriteOnly strings.
 Note that ReadWrite does not imply fully readable or writable
"""
kDS1AttrReadOnlyNode = "dsAttrTypeStandard:ReadOnlyNode"

"""
 kDS1AttrRecordImage
 A binary image of the record and all it's attributes.
 Has never been supported.
"""
kDS1AttrRecordImage = "dsAttrTypeStandard:RecordImage"

"""
 kDS1AttrSMBGroupRID
 Attributefor supporting PDC SMB interaction.
"""
kDS1AttrSMBGroupRID = "dsAttrTypeStandard:SMBGroupRID"

"""
 kDS1AttrTimePackage
 Data of Create, Modify, Backup time in UTC.
"""
kDS1AttrTimePackage = "dsAttrTypeStandard:TimePackage"

"""
 kDS1AttrTotalSize
 checksum/meta data.
"""
kDS1AttrTotalSize = "dsAttrTypeStandard:TotalSize"

"""
 kDSNAttrAllNames
 Backward compatibility only - all possible names for a record.
 Has never been supported.
"""
kDSNAttrAllNames = "dsAttrTypeStandard:AllNames"

"""
 kDSNAttrAuthMethod
 Authentication method for an authentication capable record.
"""
kDSNAttrAuthMethod = "dsAttrTypeStandard:AuthMethod"

"""
 kDSNAttrMetaNodeLocation
 Meta attribute returning registered node name by directory node plugin.
"""
kDSNAttrMetaNodeLocation = "dsAttrTypeStandard:AppleMetaNodeLocation"

"""
 kDSNAttrNodePath
 Sub strings of a Directory Service Node given in order.
"""
kDSNAttrNodePath = "dsAttrTypeStandard:NodePath"

"""
 kDSNAttrPlugInInfo
 Information (version, signature, about, credits, etc.) about the plug-in
 that is actually servicing a particular directory node.
 Has never been supported.
"""
kDSNAttrPlugInInfo = "dsAttrTypeStandard:PlugInInfo"

"""
 kDSNAttrRecordAlias
 No longer supported in Mac OS X 10.4 or later.
"""
kDSNAttrRecordAlias = "dsAttrTypeStandard:RecordAlias"

"""
 kDSNAttrRecordType
 Single Valued for a Record, Multi-valued for a Directory Node.
"""
kDSNAttrRecordType = "dsAttrTypeStandard:RecordType"

"""
 kDSNAttrSchema
 List of attribute types.
"""
kDSNAttrSchema = "dsAttrTypeStandard:Scheama"

"""
 kDSNAttrSetPasswdMethod
 Retained only for backward compatibility.
"""
kDSNAttrSetPasswdMethod = "dsAttrTypeStandard:SetPasswdMethod"

"""
 kDSNAttrSubNodes
 Attribute of a node which lists the available subnodes
        of that node.
"""
kDSNAttrSubNodes = "dsAttrTypeStandard:SubNodes"

"""
 kStandardSourceAlias
 No longer supported in Mac OS X 10.4 or later.
"""
kStandardSourceAlias = "dsAttrTypeStandard:AppleMetaAliasSource"

"""
 kStandardTargetAlias
 No longer supported in Mac OS X 10.4 or later.
"""
kStandardTargetAlias = "dsAttrTypeStandard:AppleMetaAliasTarget"

"""
 kDSNAttrNetGroupTriplet
 Multivalued attribute that defines the host, user and domain triplet combinations
  to support NetGroups.  Each attribute value is comma separated string to maintain the
  triplet (e.g., host,user,domain).
"""
kDSNAttrNetGroupTriplet = "dsAttrTypeStandard:NetGroupTriplet"


# Search Node attribute type Constants


"""
 Search Node attribute type Constants
"""

"""
 kDS1AttrSearchPath
 Search path used by the search node.
"""
kDS1AttrSearchPath = "dsAttrTypeStandard:SearchPath"

"""
 kDSNAttrSearchPath
 Retained only for backward compatibility.
"""
kDSNAttrSearchPath = "dsAttrTypeStandard:SearchPath"

"""
 kDS1AttrSearchPolicy
 Search policy for the search node.
"""
kDS1AttrSearchPolicy = "dsAttrTypeStandard:SearchPolicy"

"""
 kDS1AttrNSPSearchPath
 Automatic search path defined by the search node.
"""
kDS1AttrNSPSearchPath = "dsAttrTypeStandard:NSPSearchPath"

"""
 kDSNAttrNSPSearchPath
 Retained only for backward compatibility.
"""
kDSNAttrNSPSearchPath = "dsAttrTypeStandard:NSPSearchPath"

"""
 kDS1AttrLSPSearchPath
 Local only search path defined by the search node.
"""
kDS1AttrLSPSearchPath = "dsAttrTypeStandard:LSPSearchPath"

"""
 kDSNAttrLSPSearchPath
 Retained only for backward compatibility.
"""
kDSNAttrLSPSearchPath = "dsAttrTypeStandard:LSPSearchPath"

"""
 kDS1AttrCSPSearchPath
 Admin user configured custom search path defined by the search node.
"""
kDS1AttrCSPSearchPath = "dsAttrTypeStandard:CSPSearchPath"

"""
 kDSNAttrCSPSearchPath
 Retained only for backward compatibility.
"""
kDSNAttrCSPSearchPath = "dsAttrTypeStandard:CSPSearchPath"
