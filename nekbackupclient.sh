#!/bin/bash

#
# Contacts NekBackupMonitor and adds a report
# 
# $1: Backup Name (local name)
# 
# $2: Result Code to be send
#     0 = ERROR
#     1 = DONE
#     2 = DONE AND VERIFIED
#     3 = DONE BUT VERIFICATION ERROR
# $3: Message to be send
#

# The hostname that SSH will use (usually configured in .ssh/config)
NEKBACKUPMONITORHOSTNAME="cloud1backup_nbm";
EMAIL="jkoutsoumpas@imageaccesscorp.com";
HOSTNAME=$(hostname);

print_help() {
  printf "Usage: %s: -n <string> -c <string> -d <string> [-r int] [-m <string>]\n" "$0"
  echo "NOTE: If the -m is ommitted, then message is read from the stdin, if any"
  echo "  -n    Backup Name"
  echo "  -c    Result Code"
  echo "  -d    (optional) Duration of backup in seconds"
  echo "  -m    (optional) read the message from the value instead of stdin"
}

# make sure that ssh is available
if ! command -v ssh &> /dev/null; then
  echo "ERROR: ssh command not found." >&2;
  exit 3;
fi

while getopts "n:c:d:r:m:" o
do
    case "$o" in
    n)    BACKUPNAME="$OPTARG";;
    c)    NBMRESULTCODE="$OPTARG";;
    r)    NBMDURATION="$OPTARG";;
    d)    REPORTDATE="$OPTARG";;
    m)    NBMREPORTMESSAGE="$OPTARG";;

    ?)    
          # print_help
          exit 2
          ;;
    esac
done

if [ -z "$BACKUPNAME" ]; then
  # print_help
  echo "Backupname is required"
  exit 1
fi
if [ -z "$NBMRESULTCODE" ]; then
  # print_help
  echo "Result code is required"
  exit 1
fi

if [ -z "$NBMREPORTMESSAGE" ]; then
  # echo "no message from the -m CLI argument"

  # this tests if stdin is opened on a terminal (a tty) or not (stdin has been piped to another command)
  if [ -t 0 ]; then
    echo "not reading from stdin, because it is not piped";
  else
    echo "reading message from piped stdin";
    read -r -d '' NBMREPORTMESSAGE;
    echo "got message from the stdin";
  fi
  # NBMREPORTMESSAGE=$(</dev/stdin);
else
  echo "got message from the -m CLI argument";
fi

NBMBACKUPDATE="$(date +"%Y-%m-%d %H:%M:%S")";

if [ -n "$REPORTDATE" ]; then
  NBMBACKUPDATE="$REPORTDATE";
fi

# read -r -d '' NBACKUPMONITOR_ARGS <<'EOT'
# add $SCHEDULEID "$NBMBACKUPDATE" $NBMRESULTCODE $NBMDURATION -m "$NBMREPORTMESSAGE"
# EOT

echo "BACKUPNAME: $BACKUPNAME"
echo "NBMRESULTCODE: $NBMRESULTCODE"
echo "NBMBACKUPDATE: $NBMBACKUPDATE"
echo "NBMDURATION: $NBMDURATION"

if [ -n "$NBMREPORTMESSAGE" ]; then
  messagelen=${#NBMREPORTMESSAGE}

  # if the message is less than 100 chars (or bytes depending the LOCALE), print it
  if [[ $messagelen -lt 100 ]]; then
    echo "$NBMREPORTMESSAGE"
  else
    echo "NBMREPORTMESSAGE: <not displayed> string length is $messagelen chars"
  fi
fi

if ! command -v mail &> /dev/null; then
  echo "mail command could not be found. Will skip sending email";
fi

# in addition to the usual report to NBM, check if there is an error and immediately notify via email the admin
if [[ "$NBMRESULTCODE" -eq 0 ]]; then
  echo "$NBMREPORTMESSAGE" | mail -s "ERROR! $HOSTNAME: Backup $BACKUPNAME" $EMAIL;
elif [[ "$NBMRESULTCODE" -eq 3 ]]; then
  echo "$NBMREPORTMESSAGE" | mail -s "$HOSTNAME: $BACKUPNAME backup done BUT VERIFICATION ERROR!" $EMAIL;
fi

# echo $NBACKUPMONITOR_ARGS;
# export NBACKUPMONITOR_ARGS;

CO1OUTPUT=$(echo "$NBMREPORTMESSAGE" | ssh "$NEKBACKUPMONITORHOSTNAME");
CO1RC=$?;

unset NBACKUPMONITOR_ARGS;

if [ $CO1RC -ne 0 ]; then
  cat <<EOT error: "$CO1OUTPUT"
EOT
  echo -e "$CO1OUTPUT" | mail -s "$HOSTNAME: $BACKUPNAME backup could not contact NekBackupMonitor." $EMAIL;
fi

return $CO1RC;
