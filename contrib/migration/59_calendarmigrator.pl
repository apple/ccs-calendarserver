#!/usr/bin/perl
# Copyright 2009 Apple. All rights reserved.
## Migration Script for iCal Server

##################   Input Parameters  #######################
# --purge <0 | 1>	"1" means remove any files from the old system after you've migrated them, "0" means leave them alone.
# --sourceRoot <path>	The path to the root of the system to migrate
# --sourceType <System | TimeMachine>	Gives the type of the migration source, whether it's a runnable system or a 
#                                       Time Machine backup.
# --sourceVersion <ver>	The version number of the old system (like 10.4.11 or 10.6). Since we support migration from 10.4, 10.5, 
#                       and other 10.6 installs, it's useful to know this information, and it would be easier for me to figure 
#                       it out once and pass it on to each script than to have each script have to figure it out itself.
# --targetRoot <path>	The path to the root of the new system. Pretty much always "/"
# --language <lang>	A language identifier, such as "en." Long running scripts should return a description of what they're doing 
#                   ("Migrating Open Directory users"), and possibly provide status update messages along the way. These messages 
#                   need to be localized into the language of the SkiLift computer (which is not necessarily the server running 
#                   the migration script). This argument will identify the SkiLift language. As an alternative to doing 
#                   localization yourselves (which is a pain in scripts and command line tools), you can submit the strings to me 
#                   for localization and always send them in English, but in case you want to do it yourself, you'll need this 
#                   identifier.

#use strict;
use File::Basename;

#################################   Constants  #################################
my $CAT = "/bin/cat";
my $CP = "/bin/cp";
my $DSCL = "/usr/bin/dscl";
my $DU = "/usr/bin/du";
my $ECHO = "/bin/echo";
my $GREP = "/usr/bin/grep";
my $LAUNCHCTL = "/bin/launchctl";
my $MKDIR = "/bin/mkdir";
my $MV = "/bin/mv";
my $PLISTBUDDY = "/usr/libexec/PlistBuddy";
my $SERVERADMIN="/usr/sbin/serveradmin";

#################################   PATHS  #################################
my $migrationScriptPath = "/usr/libexec";
my $logPath = "/Library/Logs/Migration/calendarmigrator.log";
my $sharedLogPath = "/Library/Logs/Setup.log";
my $SYSTEM_PLIST = "/System/Library/CoreServices/SystemVersion.plist";
my $SERVER_PLIST = "/System/Library/CoreServices/ServerVersion.plist";
my $CALENDAR_LAUNCHD_PREFERENCES = "/System/Library/LaunchDaemons/org.calendarserver.calendarserver.plist";
my $LAUNCHD_OVERRIDES = "/var/db/launchd.db/com.apple.launchd/overrides.plist";

my $OLD_SYSTEM_PLIST;
my $OLD_SERVER_PLIST;

#################################  GLOBALS #################################
my $gPurge="0";		# Default is don't purge
my $gSourceRoot="/Previous System";
my $gSourceType="";
my $gSourceVersion="";
my $gTargetRoot="/";
my $gLanguage="en";	# Default is english
my $gStatus = 0;		# 0 = success, > 0 on failure
my $DEBUG = 0;
my $FUNC_LOG = 0;

my $SYS_VERS="0";   #10.4.11
my $SYS_MAJOR="0";  #10
my $SYS_MINOR="0";  # 4
my $SYS_UPDATE="-"; #11
my $SRV_VERS="0";   #10.4.11
my $SRV_MAJOR="0";  #10
my $SRV_MINOR="0";  # 4
my $SRV_UPDATE="-"; #11

my $MINVER="10.4"; # => 10.4
my $MAXVER="10.6"; # <  10.6

my $LANGUAGE = "en"; # Should be Tier-0 only in iso format [en, fr, de, ja], we default this to English, en.
my $PURGE = 0;       # So we will be default copy the items if there's no option specified.
my $VERSION = "";    # This is the version number of the old system passed into us by Server Assistant. [10.4.x, 10.5.x, and potentially 10.6.x]
my $ServiceName="calendar";

my $ICAL_DISABLED = ""; # Current state of service
my $ICAL_DISABLED_ORIG = "";  # State of service on source volume

if ( (defined($ENV{DEBUG})) && ($ENV{DEBUG} eq 1) ) {$DEBUG = '1';}
if ( (defined($ENV{FUNC_LOG})) && ($ENV{FUNC_LOG} eq 1) ) {$FUNC_LOG = '1';}

&ParseOptions();

if ($DEBUG) 
	{ &dumpAssociativeArray(@ARGV); }

&validateOptionsAndDispatch(@ARGV);
exit($gStatus);


##################   Functions   #######################

################################################################################
#
################################################################################
sub migrateUpgrade() {
	if ($FUNC_LOG) { print("migrateUpgrade : S\n"); }
	&logMessage("migrateUpgrade := S");

    ## Need to fix up the paths we care about with the --sourceRoot we received
	$OLD_SYSTEM_PLIST =  $gSourceRoot . $SYSTEM_PLIST;
	$OLD_SERVER_PLIST =  $gSourceRoot . $SERVER_PLIST;

	if ($DEBUG) {
		print($OLD_SYSTEM_PLIST . "\n");
		print($OLD_SERVER_PLIST . "\n");
	}

	# Get old server version parts
	if ($DEBUG) {printf("sourceVersion := %s\n", $gSourceVersion);}
	&serverVersionParts($gSourceVersion);

	if (! -e $PLISTBUDDY) {
		print "ERROR: \"$PLISTBUDDY\" does not exist.\n";
		exit(1);
	}

	# Get previous system state
	$ICAL_DISABLED_ORIG = qx(${PLISTBUDDY} -c \"Print :Disabled\" \"${gSourceRoot}${CALENDAR_LAUNCHD_PREFERENCES}\");
	chomp($ICAL_DISABLED_ORIG);
	if ($ICAL_DISABLED_ORIG ne "true") {
		$ICAL_DISABLED_ORIG = "false";
	}
	&logMessage("migrateUpgrade: source volume has Disabled = $ICAL_DISABLED_ORIG");

	# Get new system state...
	# ...by first checking the launchd overrides.plist file...
	if (-e $LAUNCHD_OVERRIDES) {
		$RESULT = qx(${PLISTBUDDY} -c \"Print :org.calendarserver.calendarserver:Disabled\" \"${LAUNCHD_OVERRIDES}\");
		chomp($RESULT);
		if (($RESULT eq "true") || ($RESULT eq "false")) {
			# we have an answer -- that key does exist in the overrides.plist
			$ICAL_DISABLED = $RESULT;
		}
	}
	# ...and then by checking launchd preferences file for the service...
	if ($ICAL_DISABLED eq "") {
		$ICAL_DISABLED = qx(${PLISTBUDDY} -c \"Print :Disabled\" \"${CALENDAR_LAUNCHD_PREFERENCES}\");
		chomp($ICAL_DISABLED);
		if ($ICAL_DISABLED ne "true") {
			$ICAL_DISABLED = "false";
		}
	}

	if (($ICAL_DISABLED_ORIG eq "false") && ($ICAL_DISABLED eq "true")) {
		&logMessage("migrateUpgrade: Starting Calendar service");
		&startStopiCal("start");
	} elsif (($ICAL_DISABLED_ORIG eq "true") && ($ICAL_DISABLED eq "false")) {
		&logMessage("migrateUpgrade: Stopping Calendar service");
		&startStopiCal("stop");
	}
		
	if ($FUNC_LOG) { print("migrateUpgrade : E\n"); }
	&logMessage("migrateUpgrade := E");
}


################################################################################
##
sub startStopiCal()
{
	my $command = shift;
    
	if ($FUNC_LOG) {printf("startStopiCal := S\n");}
	&logMessage("startStopiCal := S");

	if (($command eq "start") &&
			($ICAL_DISABLED eq "true")) {
		&logMessage("Starting Calendar service");
		qx(${SERVERADMIN} start ${ServiceName});
		if ($? != 0) { &logMessage("${SERVERADMIN} failed with status error status: $?\n"); }
		if ($DEBUG) { printf("%s\n", qq(${SERVERADMIN} start ${ServiceName})); }
	} elsif (($command eq "stop") &&
			($ICAL_DISABLED eq "false")) { 
		&logMessage("Stopping Calendar service");
		qx(${SERVERADMIN} stop ${ServiceName});
		if ($? != 0) { &logMessage("${SERVERADMIN} failed with status error status: $?\n"); }
		if ($DEBUG) { printf("%s\n", qq(${SERVERADMIN} stop ${ServiceName}));  }
	} else {
		if ($DEBUG) { &logMessage("startStopiCal: nop, command = $command, ICAL_DISABLED = $ICAL_DISABLED"); }
	}
	
	if ($FUNC_LOG) {printf("startStopiCal := E\n");}
	&logMessage("startStopiCal := E");	
}

  
################################################################################
## Service-specific log	
sub logMessage()
{
	if (! open(LOGFILE, ">>$logPath")) {
		print "$0: cannot open $logPath: $!";
		return;
	}
	my $time = localtime();
	print LOGFILE "$time: ".basename($0).": @_\n";
	print "@_\n" if $DEBUG;
	close(LOGFILE);
}

################################################################################
##We only want to run this script if the previous system version is greater than 10.4 and less than 10.6!
sub isValidVersion() 
{
    if ($FUNC_LOG) { print("isValidVersion : S\n"); }
	my $valid=0;
	if (($gSourceVersion >= "10.4.0") && ($gSourceVersion < "10.6.0")) {
		$valid = 1;
    	if ($DEBUG) {printf("valid\n");}
	} else {
		printf("Version supplied was not valid := %s\n", $gSourceVersion);
	}
    if ($FUNC_LOG) { print("isValidVersion : E\n"); }
	return($valid);
}

################################################################################
##Make sure the language suppled is one we care about!
sub isValidLanguage() 
{
    if ($FUNC_LOG) { print("isValidLanguage : S\n"); }
	my $valid=0;
    my $tLang=$gLanguage;
	if (($tLang eq "en") || ($tLang eq "fr") || ($tLang eq "de") || ($tLang eq "ja")) {
		$valid = 1;
    	if ($DEBUG) {printf("valid\n");}
	}
    if ($FUNC_LOG) { print("isValidLanguage : E\n"); }
	return($valid);
}

################################################################################
sub validateOptionsAndDispatch()
{
	my %BigList = @_;
	my $valid;
	my $nothing;

	#Set the globals with the options passed in.
	$gPurge=$BigList{"--purge"};
	$gSourceRoot=$BigList{"--sourceRoot"};
	$gSourceType=$BigList{"--sourceType"};
	$gSourceVersion=$BigList{"--sourceVersion"};
	$gTargetRoot=$BigList{"--targetRoot"};
	$gLanguage=$BigList{"--language"};
	
	qx(/bin/echo purge: $gPurge >> $sharedLogPath);
	qx(/bin/echo sourceRoot: $gSourceRoot >> $sharedLogPath);
	qx(/bin/echo sourceType: $gSourceType >> $sharedLogPath);
	qx(/bin/echo sourceVersion: $gSourceVersion >> $sharedLogPath);
	qx(/bin/echo targetRoot: $gTargetRoot >> $sharedLogPath);
	qx(/bin/echo language: $gLanguage >> $sharedLogPath);
	
	SWITCH: {
		if( (pathExists($gSourceRoot)) && (pathExists($gTargetRoot)) ) {
			if (isValidLanguage()) {
				if (isValidVersion()) {
					$valid = 1;
					migrateUpgrade();
				} else {
					print("Did not supply a valid version for the --sourceVersion parameter, needs to be >= 10.4.0 and < 10.6.0\n");
					Usage(); exit(1);
				}
			} else {
				print("Did not supply a valid language for the --language parameter, needs to be one of [en|fr|de|ja]\n");
				Usage(); exit(1);
			}
		} else {
			print("Source and|or destination for upgrade/migration does not exist.\n");
			Usage(); exit(1);
		} last SWITCH;
		$nothing = 1;
    }
    if($nothing eq 1)
  		{print("Legal options were not supplied!\n");Usage();}
}

################################################################################
#
# ParseOptions takes a list of possible options and a boolean indicating
# whether the option has a value following, and sets up an associative array
# %opt of the values of the options given on the command line. It removes all
# the arguments it uses from @ARGV and returns them in @optArgs.
#
sub ParseOptions {
    my (@optval) = @_;
    my ($opt, @opts, %valFollows, @newargs);

    while (@optval) {
		$opt = shift(@optval);
		push(@opts,$opt);
		$valFollows{$opt} = shift(@optval);
    }

    my @optArgs = ();
    my %opt = ();
	my $arg;

    arg: while (defined($arg = shift(@ARGV))) {
	foreach $opt (@opts) {
	    if ($arg eq $opt) {
		push(@optArgs, $arg);
		if ($valFollows{$opt}) {
		    $opt{$opt} = shift(@ARGV);
		    push(@optArgs, $opt{$opt});
		} else {
		    $opt{$opt} = 1;
		}
		next arg;
	    }
	}
	push(@newargs,$arg);
    }
    @ARGV = @newargs;
}

################################################################################
sub dumpAssociativeArray()
{
	my %BigList = @_;
	my $theKey;
	my $theVal;
	while(($theKey, $theVal) = each (%BigList))
		{ print "$theKey is the key for value $theVal\n"; }
}

################################################################################
##Check a path's existence!
sub pathExists() 
{
    if ($FUNC_LOG) { print("pathExists : S\n"); }
	my $exists = 0;
	my ($tPath) = @_;
   	if ($DEBUG) {printf("path := %s\n", $tPath);}
	if (-e $tPath) {
		$exists = 1;
    	if ($DEBUG) {printf("exists\n");}
	}
    if ($FUNC_LOG) { print("pathExists : E\n"); }
	return($exists);
}

################################################################################
# Get old system / server versions and parts
sub getPreviousVersions()
{
    if ($FUNC_LOG) { print("getPreviousVersions : S\n"); }
	# Get old system / server versions and parts
	my $tVer;
	if (-e $OLD_SYSTEM_PLIST) {
		$SYS_VERS=qx(${PLISTBUDDY} -c \"Print :ProductVersion:\" \"${OLD_SYSTEM_PLIST}\");
		$tVer=$SYS_VERS;
		chomp($tVer);
		print($tVer . "\n");
		my @SYS_VER_PARTS = split(/\./, $tVer);
		if ($DEBUG) {
			print($SYS_VER_PARTS[0] . "\n"); #Major
			print($SYS_VER_PARTS[1] . "\n"); #Minor
			print($SYS_VER_PARTS[2] . "\n"); #Update
		}
		$SYS_MAJOR=$SYS_VER_PARTS[0];
		$SYS_MINOR=$SYS_VER_PARTS[1];
		$SYS_UPDATE=$SYS_VER_PARTS[2];
	}
	if (-e $OLD_SERVER_PLIST) {
		$SRV_VERS=qx(${PLISTBUDDY} -c \"Print :ProductVersion:\" \"${OLD_SERVER_PLIST}\");
		$tVer=$SRV_VERS;
		chomp($tVer);
		print($tVer . "\n");
		my @SRV_VER_PARTS = split(/\./, $tVer); 
		if ($DEBUG) {
			print($SRV_VER_PARTS[0] . "\n"); #Major
			print($SRV_VER_PARTS[1] . "\n"); #Minor
			print($SRV_VER_PARTS[2] . "\n"); #Update
		}
		$SRV_MAJOR=$SRV_VER_PARTS[0];
		$SRV_MINOR=$SRV_VER_PARTS[1];
		$SRV_UPDATE=$SRV_VER_PARTS[2];
	}
    if ($FUNC_LOG) { print("getPreviousVersions : E\n"); }
}
		
################################################################################
# Get old server version parts
sub serverVersionParts()
{
	my ($VERS) = @_;
	if ($FUNC_LOG) { print("serverVersionParts : S\n"); }

	if ($DEBUG) {printf("sourceVersion := %s\n", $VERS);}
	my @SRV_VER_PARTS = split(/\./, $VERS); 
	if ($DEBUG) {
		print($SRV_VER_PARTS[0] . "\n"); #Major
		print($SRV_VER_PARTS[1] . "\n"); #Minor
		print($SRV_VER_PARTS[2] . "\n"); #Update
	}
	$SRV_MAJOR=$SRV_VER_PARTS[0];
	$SRV_MINOR=$SRV_VER_PARTS[1];
	$SRV_UPDATE=$SRV_VER_PARTS[2];

	if ($FUNC_LOG) { print("serverVersionParts : E\n"); }
}
		
# Show proper usage
sub Usage()
{
	print("--purge <0 | 1>   \"1\" means remove any files from the old system after you've migrated them, \"0\" means leave them alone." . "\n");
	print("--sourceRoot <path> The path to the root of the system to migrate" . "\n");
	print("--sourceType <System | TimeMachine> Gives the type of the migration source, whether it's a runnable system or a " . "\n");
	print("                  Time Machine backup." . "\n");
	print("--sourceVersion <ver> The version number of the old system (like 10.4.11 or 10.6). Since we support migration from 10.4, 10.5, " . "\n");
	print("                  and other 10.6 installs, it's useful to know this information, and it would be easier for me to figure " . "\n");
	print("                  it out once and pass it on to each script than to have each script have to figure it out itself." . "\n");
	print("--targetRoot <path> The path to the root of the new system. Pretty much always \"\/\"" . "\n");
	print("--language <lang> A language identifier, such as \"en.\" Long running scripts should return a description of what they're doing " . "\n");
	print("                  (\"Migrating Open Directory users\"), and possibly provide status update messages along the way. These messages " . "\n");
	print("                  need to be localized into the language of the SkiLift computer (which is not necessarily the server running " . "\n");
	print("                  the migration script). This argument will identify the SkiLift language. As an alternative to doing " . "\n");
	print("                  localization yourselves (which is a pain in scripts and command line tools), you can submit the strings to me " . "\n");
	print("                  for localization and always send them in English, but in case you want to do it yourself, you'll need this " . "\n");
	print("                  identifier." . "\n");
	print(" " . "\n");
}
