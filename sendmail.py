#!/usr/bin/python2.7
"""
----------------------------------------------------------------------
Description: Module to send HTML formatted emails. Will always be
imported.
----------------------------------------------------------------------
Author: Prasath Suthagar
Version: 0.0.2
Maintainer: Prasath Suthagar
Email: Prasath Suthagar
Status: "Development Phase"

 * Copyright (C) All Rights Reserved
 * Proprietary and confidential
"""
import sys
import logging
import argparse
import os
from datetime import datetime
from getpass import getuser
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


# Global variables
# Set logger name
logger = logging.getLogger(__name__)
# Today's date in file constructor format 20220506
fdate = str(datetime.now().strftime("%Y%m%d"))
# Current time in file constructor format 184315
ftime = str(datetime.now().strftime("%H%M%S"))
# Username of script caller for usage logging
username = getuser()


# FILES AND DIRECTORIES
# The top directory for the script
scriptDir = os.path.abspath(".")

# Logging directory in the script main directory, create if not made
logDir = "{}/logging".format(scriptDir)
try:
    if not os.path.isdir(logDir):
        os.makedirs(logDir)
except Exception:
    pass

# Directory of the archived files, create if not made
archiveDir = "{}/archive".format(scriptDir)
try:
    if not os.path.isdir(archiveDir):
        os.makedirs(archiveDir)
except Exception:
    pass


def create_parser():
    """ Create a parser which will enable different features to be added to the script.
    --debug: is always created to allow the user to add debugging outputs to the log file without changing the user experience.

    Args:
        level: 'INFO' by default, can be 'DEBUG' if user passes --debug on cli
    Returns:
        logger: Creates a global logger so log doesn't need to be passed between modules
    Raises:
        N/A
    """
    parser = argparse.ArgumentParser(description='')
    parser.add_argument("--debug", help="Turn on extra debugging to log file", action="store_true")
    args = parser.parse_args()
    if args.debug:
        create_logger('DEBUG')
    else:
        create_logger()
    logger.info(args)
    return(args)


def create_logger(level='INFO'):
    """ This function creates a logger for the script to log too. Using the name of the script it creates a file named
    log.<scriptname>. for example if the script is called basic.py then the log will be called log.basic.
    The logger is set to global so that any function in the script can log to it without having to pass the logger to
    every function. Set to overwrite the log file each time the script is run. Does return anything as not required.

    Args:
        level: 'INFO' by default, can be 'DEBUG' if user passes --debug on cli
    Returns:
        scriptname: the scriptname as a string with extensions and dirs stripped. carln/main.py would return main
    Raises:
        N/A
    """
    # Used to take the executed function and remove any extension/s and leading directories and return the raw name
    # of the function to give the script name. e.g dir/advanced.py will return advanced.
    global scriptname
    if "." in sys.argv[0] and "/" in sys.argv[0]:
        scriptname = sys.argv[0].split(".")[0].split('/')[-1]
    elif "." in sys.argv[0]:
        scriptname = sys.argv[0].split(".")[0]
    else:
        scriptname = sys.argv[0]
    log_name = "{}/log.{}".format(scriptDir, scriptname)
    if level == 'INFO':
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s:%(levelname)s:%(name)s:%(funcName)s:%(message)s',
                            filename=log_name,
                            filemode='w')
    elif level == 'DEBUG':
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s:%(levelname)s:%(name)s:%(funcName)s:%(message)s',
                            filename=log_name,
                            filemode='w')
    logger.info('Logger Created called {}'.format(scriptname))
    logger.info('Logger directory - {}'.format(scriptDir))


def main(emails, subject, html_body, attachments=None):
    msg = MIMEMultipart()
    msg['To'] = ", ".join(emails)
    msg['From'] = os.environ.get("SMTP_FROM", "QoS Traffic Generator <noreply@example.com>")
    msg['Subject'] = subject

    html_style = """<!DOCTYPE HTML PUBLIC -//W3C//DTD HTML 4.01 Transitional//EN http://www.w3.org/TR/html4/loose.dtd>
    <html>
    <!-- CSS STYLE -->
    <head><style>
    h2.heading {color:Red; background-color:#f2f2f2; border-style:solid; border-width:10px 30px; border-color:#f2f2f2; }
    p.restricted {color:Red; background-color:#f2f2f2; border-style:solid; border-width:5px 10px; border-color:#f2f2f2;}
    p.logs { border-style:solid; border-width:1px; padding:5px; font-family:"Courier New", Arial; background-color:#f2f2f2; width:90%; margin-left:20px}
    a {color:Red}
    table, th, td {border: 1px solid black; border-collapse: collapse;}
    td {text-align: center}
    th {color:#FFFFFF; background-color:red;}
    </style></head>"""

    html_header = """<!-- HEADER AREA -->
    <h2 class="heading"> {} </h2>
    """.format(subject)

    html_footer = """<!-- FOOTER AREA -->
    <p>Please contact the system administrator with any questions/queries about this email.</p>
    <!-- RESTRICTED TEXT AREA -->
    <p class="restricted">Confidential - Internal Use Only</p>
    """

    html_message = html_style
    html_message += html_header
    html_message += html_body
    html_message += html_footer

    body = MIMEText(html_message, 'html', 'utf-8')
    msg.attach(body)  # add message body (text or html)

    if attachments is not None:
        for f in attachments:  # add files to the message
            logger.info(f)
            file = f.split('/')[-1]
            attachment = MIMEApplication(open(f, "rb").read(), _subtype="txt")
            attachment.add_header('Content-Disposition','attachment', filename=file)
            msg.attach(attachment)

    smtp_host = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "25"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_use_tls = os.environ.get("SMTP_TLS", "false").lower() == "true"
    smtp_use_ssl = os.environ.get("SMTP_SSL", "false").lower() == "true"

    try:
        if smtp_use_ssl or smtp_port == 465:
            logger.info("Connecting via SSL to {}:{}".format(smtp_host, smtp_port))
            s = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            logger.info("Connecting via SMTP to {}:{}".format(smtp_host, smtp_port))
            s = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            if smtp_use_tls or smtp_port == 587:
                logger.info("Starting TLS negotiation...")
                s.starttls()
                
        if smtp_user and smtp_pass:
            logger.info("Authenticating SMTP user: {}".format(smtp_user))
            s.login(smtp_user, smtp_pass)
            
        s.sendmail(msg['From'], emails, msg.as_string())
        logger.info('Email sent successfully!')
        s.close()
    except Exception as e:
        logger.error('Failed to send email via SMTP: {}'.format(e))
        raise e


if __name__ == '__main__':
    try:
        global args
        args = create_parser()
        main()
    except KeyboardInterrupt:
        print("User manually ended script")

