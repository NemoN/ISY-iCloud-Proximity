#!/opt/local/bin/python2.7
############################################################################################################
## LIBRARY IMPORT                                                                                          #
############################################################################################################
###Imports for logging
import logging
import signal
import traceback
import logging, sys, logging.handlers
from logging.handlers import SysLogHandler
import socket, os, time, datetime
import subprocess

### requests library
try:
	import requests
except:
	print "Startup: Failed to import the requests library. Please make sure it's installed. You can try 'pip install requests'."
	exit(1)	

### Database library
try:
	import peewee as pw
	from playhouse.migrate import *
except:
	print "Startup: Failed to import the Peewee library. Please make sure it's installed. You can try 'pip install peewee'."
	exit(1)	

### iCloud imports:
try:
	from pyicloud import PyiCloudService
	import click
except:
	print "Startup: Failed to import the pyicloud library. Please make sure it's installed. You can try 'pip install pyicloud'."
	exit(1)

### Programatic stuff
import json, urllib2, xmltodict
from collections import OrderedDict

### For geofencing
try:
	from geopy.distance import vincenty
except:
	print "Startup: Failed to import the geopy library. Please make sure it's installed. You can try 'pip install geopy'."
	exit(1)
	
### For reading .ini files
from ConfigParser import SafeConfigParser

### library for operating system detection
try:
	import platform
except:
	print "Startup: Failed to import the platform libray to determine the operating system, assuming linux."

### Determine OS before proceding farther:
try:
	opsys = str(platform.system()).lower()
	print "Startup: Your current operating system is {}".format(opsys)
except:
	print "Startup: Could not determine your operating system, setting to linux."
	opsys = "linux"
############################################################################################################
## LOGGING CONFIGURATION                                                                                   #
############################################################################################################
# Logging configuration load:
try:
	application_logging_name = 'iPhoneLocation'
	pid = os.getpid()
	print "Startup: PID={}".format(pid)
	if opsys == 'linux' or opsys == 'darwin':
		f_out = open('/tmp/{}.pid'.format(application_logging_name), 'w', 0)
	elif opsys == 'windows':
		f_out = open('c:\{}.pid'.format(application_logging_name), 'w', 0)		
	f_out.write(str(pid))
	f_out.flush
	f_out.close
	if opsys == 'linux' or opsys == 'darwin':
		print "Startup: Created pidfile at /tmp/{}.pid".format(application_logging_name)
	elif opsys == 'windows':
		print "Startup: Created pidfile at c:\{}.pid".format(application_logging_name)
	try:
		proc = subprocess.Popen(['git', 'describe'], stdout=subprocess.PIPE)
		service_version = proc.communicate()[0].strip()
	except:
		try:
			status_output, returncode = git('status')
			status_output_split = status_output.split('\n')
			local_git_branch = status_output_split[0].split()[2]
			service_version = local_git_branch
		except:
			service_version = 'vX.X'
	print "Startup: {} Version: {}".format(application_logging_name, service_version)
	print "Startup: Loading application logging settings."

	class ContextFilter(logging.Filter):
		hostname = socket.gethostname()

		def filter(self, record):
			record.hostname = ContextFilter.hostname
			record.timestamp = time.time()
			record.ec2app001_application_name = application_logging_name
			record.application_name = application_logging_name
			record.application_version = service_version
			record.error_level_name = record.levelname
			record.error_level_number = record.levelno
			record.application_runtime = record.msecs
			record.msg = '{} {}({})[{}]: {} - {}'.format(record.hostname, record.application_name, record.application_version, pid, record.levelname.ljust(8), record.msg)
			return True

	f = ContextFilter()

	if not os.path.exists('./conf/logging.conf') and not os.path.isdir('./conf/logging.conf'):
		print "Startup: logging.conf does not exist. Assuming production values."
		def loggingconfig():
			# Basic logging config
			global logger
			logger = logging.getLogger('{}'.format(application_logging_name))
			logger.addFilter(f)


			# check to see if the logs directory exists, if not, create it:
			if not os.path.exists('./logs') and not os.path.isdir('./logs'):
				os.makedirs('./logs')

			# create a file handler
			file_handler = logging.handlers.WatchedFileHandler('./logs/{}.log'.format(application_logging_name), mode='a')
			file_handler.setLevel(logging.DEBUG)

			#create a stream handler
			stream_handler = logging.StreamHandler(sys.stdout)
			stream_handler.setLevel(logging.INFO)

			# create a logging format
			formatter = logging.Formatter('%(asctime)s - %(message)s')
			file_handler.setFormatter(formatter)

			class OneLineExceptionFormatter(logging.Formatter):
				def formatException(self, exc_info):
					result = super(OneLineExceptionFormatter, self).formatException(exc_info)
					return repr(result) # or format into one line however you want to

				def format(self, record):
					s = super(OneLineExceptionFormatter, self).format(record)
					if record.exc_text:
						s = s.replace('\n', '|')
						s = s.split('|')[0]
					return s

			formatter_custom_exc_info = OneLineExceptionFormatter('%(asctime)s - %(message)s')
			stream_handler.setFormatter(formatter_custom_exc_info)

			# Set the basic logging level for the entire app
			logger.setLevel(logging.DEBUG)

			# add the handlers to the logger
			logger.addHandler(file_handler)
			logger.addHandler(stream_handler)
	else:
		print "Startup: logging.conf exists. Using that."
		execfile('./conf/logging.conf')
	loggingconfig()
	logger.info('INIT - Loaded logging settings, the application is starting.')
except:
	print "Startup: Failed to load logging settings, ABORTING!"
	print traceback.format_exc()
	sys.exit(1)
############################################################################################################
## CLASS DEFINITIONS                                                                                       #
############################################################################################################
#
############################################################################################################
## EARLY FUNCTION LOADING                                                                                  #
############################################################################################################
### Function to automatically restart the application if some unrecoverable error occurs:
def program_restart():
	logger.info('RESTART - Executing restart in 10 seconds...')
	logger.debug('RESTART - Pause for 10 seconds to settle.')
	time.sleep(10)
	python = sys.executable
	os.execl(python, python, * sys.argv)
#
############################################################################################################
## CONFIGURATION VARIABLES                                                                                 #
############################################################################################################
#
### Read configuration items:
try:
	### Define global variables early to avoid sytax checking errors:
	global db_conf
	global isy_conf
	global openhab_conf
	global icloudapi_conf
	global device_conf
	global general_conf
	### Check to see if config file exists:
	if os.path.isfile("./conf/iphonelocation.ini"):
		logger.debug('MAIN - iphonelocation.ini exists, continuing.')
	else:
		logger.error("MAIN - iphonelocation.ini does not exist or can't be read. Exiting!")
		exit()

	### Add rules here to check for sections, versions and options:
	try:
		### Initial creation of the config parser object once we know the file is there.
		parser = SafeConfigParser()
		parser.read('./conf/iphonelocation.ini')
	except:
		logger.error('MAIN - There was an error reading your config file.', exc_info=True)
		
	try:
		if parser.has_section('ini_version'):
			logger.info('MAIN - CONFIG_READ - ini_version section present.')
			section_ini_version = True
			config_file_version = int(parser.get('ini_version', 'version'))
		else:
			logger.info('MAIN - CONFIG_READ - ini_version section not present.')
			section_ini_version = False
			config_file_version = 0
		logger.info('MAIN - CONFIG_READ - Config file version: {}'.format(config_file_version))
		if parser.has_section('database'):
			logger.info('MAIN - CONFIG_READ - database section present.')
			section_database = True
		else:
			logger.info('MAIN - CONFIG_READ - database section not present.')
			section_database = False
		if parser.has_section('ISY'):
			logger.info('MAIN - CONFIG_READ - ISY section present.')
			section_isy = True
		else:
			logger.info('MAIN - CONFIG_READ - ISY section not present.')
			section_isy = False
		if parser.has_section('openHAB'):
			logger.info('MAIN - CONFIG_READ - openHAB section present.')
			section_openhab = True
		else:
			logger.info('MAIN - CONFIG_READ - openHAB section not present.')
			section_openhab = False
		if parser.has_section('iCloudAPI'):
			logger.info('MAIN - CONFIG_READ - iCloudAPI section present.')
			section_icloudapi = True
		else:
			logger.info('MAIN - CONFIG_READ - iCloudAPI section not present.')
			section_icloudapi = False
		if parser.has_section('device'):
			logger.info('MAIN - CONFIG_READ - device section present.')
			section_device = True
		else:
			logger.info('MAIN - CONFIG_READ - device section not present.')
			section_device = False
		if parser.has_section('general'):
			logger.info('MAIN - CONFIG_READ - general section present.')
			section_general = True
		else:
			logger.info('MAIN - CONFIG_READ - general section not present.')
			section_general = False
	except:
		logger.error('MAIN - CONFIG_READ - There was an error checking for sections in your config file.', exc_info=True)
		pass
	
	if section_ini_version == False and config_file_version < 3:
		logger.info('MAIN - CONFIG_READ - You are currently not on the configuration version control system.')
		logger.info('MAIN - CONFIG_READ - The script will read your current config items, rename your old .ini file and create a ' +
					'new version controlled file with all of your current settings and set you on version 3 of the config file.')
		config_file_version = 3
		### Read database configuration:
		if section_database == True:
			try:
				global db_conf
				db_conf = {}
				db_conf['enabled'] = parser.getboolean('database', 'enabled')
				db_conf['name'] = parser.get('database', 'database')
				db_conf['host'] = parser.get('database', 'host')
				db_conf['port'] = int(parser.get('database', 'port'))
				db_conf['user'] = parser.get('database', 'user')
				db_conf['passwd'] = parser.get('database', 'passwd')
				logger.debug('MAIN - db_conf: {}'.format(db_conf))
			except:
				logger.error('MAIN - Error reading settings from iphonelocation.ini in your [database] section. You may need to start wiith a new .ini \
							 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
							 Exiting!', exc_info = True)
				exit(1)
		else:
			logger.error('MAIN - You need to have a fully complete [database] section of your current .ini file.')
			exit(1)
				
		### Read ISY configuration:
		if section_isy == True:
			try:
				### Grab the ISY connection settings:
				global isy_conf
				isy_conf = {}
				isy_conf['enabled'] = parser.getboolean('ISY', 'enabled')
				isy_conf['username'] = parser.get('ISY', 'username')
				isy_conf['password'] = parser.get('ISY', 'password')
				isy_conf['hostname'] = parser.get('ISY', 'hostname')
				isy_conf['port'] = int(parser.get('ISY', 'port'))
				isy_conf['SSL'] = parser.getboolean('ISY', 'SSL')
				isy_conf['WifiVAR'] = parser.get('ISY', 'WifiVAR')
				isy_conf['WifiVAR_Expected'] = int(parser.get('ISY', 'WifiVAR_Expected'))
				isy_conf['BtVAR'] = parser.get('ISY', 'BtVAR')
				isy_conf['BtVAR_Expected'] = int(parser.get('ISY', 'BtVAR_Expected'))
				isy_conf['DistanceVAR'] = parser.get('ISY', 'DistanceVAR') 
				logger.debug('MAIN - isy_conf: {}'.format(isy_conf))
			except:
				logger.error('MAIN - Error reading settings from iphonelocation.ini in your [ISY] section. You may need to start wiith a new .ini \
							 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
							 Exiting!', exc_info = True)
				exit(1)
		else:
			logger.error('MAIN - You need to have a fully complete [ISY] section of your current .ini file.')
			exit(1)
	
		### Read openHAB configuration:
		global openhab_conf
		if section_openhab == True:
			try:
				### Grab the ISY connection settings:
				openhab_conf = {}
				openhab_conf['enabled'] = parser.getboolean('openHAB', 'enabled')
				openhab_conf['authentication'] = parser.getboolean('openHAB', 'authentication')
				openhab_conf['username'] = parser.get('openHAB', 'username')
				openhab_conf['password'] = parser.get('openHAB', 'password')
				openhab_conf['hostname'] = parser.get('openHAB', 'hostname')
				openhab_conf['port'] = int(parser.get('openHAB', 'port'))
				openhab_conf['SSL'] = parser.getboolean('openHAB', 'SSL')
				openhab_conf['item_name'] = parser.get('openHAB', 'item_name')
				logger.debug('MAIN - openhab_conf: {}'.format(openhab_conf))	
			except:
				logger.error('MAIN - Error reading settings from iphonelocation.ini in your [openHAB] section. You may need to start wiith a new .ini \
							 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
							 Exiting!', exc_info = True)
				exit(1)
		else:
			logger.info('MAIN - You do not have a current [openHAB] section of your .ini file. A new one with defualt values will be added for you.')	
			openhab_conf = {}
			openhab_conf['enabled'] = False
			openhab_conf['authentication'] = False
			openhab_conf['username'] = 'myusername'
			openhab_conf['password'] = 'mypassword'
			openhab_conf['hostname'] = '111.222.333.444'
			openhab_conf['port'] = 8080
			openhab_conf['SSL'] = False
			openhab_conf['item_name'] = 'My_Distance_Item_Name'
			logger.debug('MAIN - openhab_conf: {}'.format(openhab_conf))
	
		### Read the iCloud configuration:
		if section_icloudapi == True:
			try:
				### Grab the iCloud API authentication settings:
				global icloudapi_conf
				icloudapi_conf = {}
				icloudapi_conf['username'] = parser.get('iCloudAPI', 'username')
				icloudapi_conf['password'] = parser.get('iCloudAPI', 'password')
				logger.debug('MAIN - icloudapi_conf: {}'.format(icloudapi_conf))
			except:
				logger.error('MAIN - Error reading settings from iphonelocation.ini in your [iCloudAPI] section. You may need to start wiith a new .ini \
							 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
							 Exiting!', exc_info = True)
				exit(1)
		else:
			logger.error('MAIN - You need to have a fully complete [iCloudAPI] section of your current .ini file.')
			exit(1)
	
		### Read the device settings:
		if section_device == True:
			try:
				global device_conf
				device_conf = {}
				device_conf['name'] = parser.get('device', 'name')
				device_conf['shortname'] = parser.get('device', 'shortname')
				device_conf['WiFiCheck'] = parser.getboolean('device', 'WiFiCheck')
				device_conf['BTCheck'] = parser.getboolean('device', 'BTCheck')
				device_conf['iCloudGUID'] = parser.get('device', 'iCloudGUID')
				device_conf['location_home_lat'] = parser.get('device', 'location_home_lat')
				device_conf['location_home_long'] = parser.get('device', 'location_home_long')
				logger.debug('MAIN - device_conf: {}'.format(device_conf))
			except:
				logger.error('MAIN - Error reading settings from iphonelocation.ini in your [device] section. You may need to start wiith a new .ini \
							 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
							 Exiting!', exc_info = True)
				exit(1)
		else:
			logger.error('MAIN - You need to have a fully complete [device] section of your current .ini file.')
			exit(1)
			
		### Read the general program options:
		if section_general ==True:
			try:
				### Grab general options:
				global general_conf
				general_conf = {}
				general_conf['numberofdevices'] = int(parser.get('general', 'numberofdevices'))
				general_conf['cycle_sleep_default'] = float(parser.get('general', 'cycle_sleep_default'))
				general_conf['cycle_sleep_withradio'] = float(parser.get('general', 'cycle_sleep_withradio'))
				general_conf['cycle_sleep_distance'] = float(parser.get('general', 'cycle_sleep_distance'))
				general_conf['cycle_sleep_variable_distance'] = float(parser.get('general', 'cycle_sleep_variable_distance'))
				general_conf['cycle_sleep_variable_modifier_default'] = float(parser.get('general', 'cycle_sleep_variable_modifier_default'))
				general_conf['cycle_sleep_variable_modifier_inbound'] = float(parser.get('general', 'cycle_sleep_variable_modifier_inbound'))
				general_conf['isy_distance_precision'] = int(parser.get('general', 'isy_distance_precision'))
				general_conf['isy_distance_multiplier'] = int(parser.get('general', 'isy_distance_multiplier'))
				general_conf['isold_reject'] = parser.getboolean('general', 'isold_reject')
				general_conf['isold_retries'] = int(parser.get('general', 'isold_retries'))
				general_conf['isold_sleep'] = int(parser.get('general', 'isold_sleep'))	
				general_conf['gpsfromcell_reject'] = parser.getboolean('general', 'gpsfromcell_reject')
				general_conf['gpsfromcell_retries'] = int(parser.get('general', 'gpsfromcell_retries'))
				general_conf['gpsfromcell_sleep'] = int(parser.get('general', 'gpsfromcell_sleep'))	
				general_conf['battery_check'] = parser.getboolean('general', 'battery_check')
				general_conf['battery_threshold'] = int(parser.get('general', 'battery_threshold'))
				general_conf['battery_sleep'] = int(parser.get('general', 'battery_sleep'))		
				general_conf['battery_retries'] = int(parser.get('general', 'battery_retries'))
				general_conf['battery_retries_sleep'] = int(parser.get('general', 'battery_retries_sleep'))
				general_conf['gps_recheck'] = parser.getboolean('general', 'gps_recheck')
				general_conf['gps_recheck_time'] = int(parser.get('general', 'gps_recheck_time'))
				### Fill in default values for new settings not preset in the configuration file:
				general_conf['battery_isy_reporting'] = False
				general_conf['battery_isy_variable'] = 0
				logger.debug('MAIN - general_conf: {}'.format(general_conf))
			except:
				logger.error('MAIN - Error reading settings from iphonelocation.ini in your [general] section. You may need to start wiith a new .ini \
							 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
							 Exiting!', exc_info = True)
				exit(1)
		else:
			logger.error('MAIN - You need to have a fully complete [general] section of your current .ini file.')
			exit(1)

		### Attempt to write out a new ini file and if complete, backup the old one and rename and use the new one.
		try:
			logger.info('MAIN - Attempting to upgrade your configuration file.')
			f_out = open('./conf/iphonelocation.ini.temp', 'w', 0)
			execfile('./iphonelocation.ini.tmpl')
			f_out.flush
			f_out.close
			logger.info('MAIN - A new configuration file was created properly, it will be moved into place and your old file backed up.')
			new_ini = True
		except:
			logger.error('MAIN - An attempt to upgrade your configuration file has failed. The script will continue with the current file.', exc_info=True)
			new_ini = False

		### If the new ini file was created properly, backup the old one, rename the new one, restart the app with the new file.
		if new_ini == True:
			ini_file_backupname = 'iphonelocation.ini.{}'.format(int(time.time()))
			os.rename('./conf/iphonelocation.ini', './conf/{}'.format(ini_file_backupname))
			logger.info('MAIN - Your old configuration file was renamed to: {}'.format(ini_file_backupname))
			os.rename('./conf/iphonelocation.ini.temp', './conf/iphonelocation.ini')
			logger.info('MAIN - Your new configuration file has been put in place, the script will now restart.')
			program_restart()

	elif section_ini_version == True:
		logger.info('MAIN - CONFIG_READ - You are on the version controlled configuration file system and your current .ini file version is: {}'.format(config_file_version))
		config_errors = False
		if config_file_version == 3:
			logger.debug('MAIN - Reading configuration settings for version 3 of the .ini file.')
			### Read database configuration:
			if section_database == True:
				try:
					db_conf = {}
					db_conf['enabled'] = parser.getboolean('database', 'enabled')
					db_conf['name'] = parser.get('database', 'database')
					db_conf['host'] = parser.get('database', 'host')
					db_conf['port'] = int(parser.get('database', 'port'))
					db_conf['user'] = parser.get('database', 'user')
					db_conf['passwd'] = parser.get('database', 'passwd')
					logger.debug('MAIN - db_conf: {}'.format(db_conf))
				except:
					logger.error('MAIN - Error reading settings from iphonelocation.ini in your [database] section. You may need to start wiith a new .ini \
								 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
								 Exiting!', exc_info = True)
					config_errors = True
			else:
				logger.error('MAIN - You need to have a fully complete [database] section of your current .ini file.')
				config_errors == True
					
			### Read ISY configuration:
			if section_isy == True:
				try:
					### Grab the ISY connection settings:
					isy_conf = {}
					isy_conf['enabled'] = parser.getboolean('ISY', 'enabled')
					isy_conf['username'] = parser.get('ISY', 'username')
					isy_conf['password'] = parser.get('ISY', 'password')
					isy_conf['hostname'] = parser.get('ISY', 'hostname')
					isy_conf['port'] = int(parser.get('ISY', 'port'))
					isy_conf['SSL'] = parser.getboolean('ISY', 'SSL')
					logger.debug('MAIN - isy_conf: {}'.format(isy_conf))
				except:
					logger.error('MAIN - Error reading settings from iphonelocation.ini in your [ISY] section. You may need to start wiith a new .ini \
								 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
								 Exiting!', exc_info = True)
					config_errors == True
			else:
				logger.error('MAIN - You need to have a fully complete [ISY] section of your current .ini file.')
				config_errors == True
		
			### Read openHAB configuration:
			if section_openhab == True:
				try:
					### Grab the ISY connection settings:
					openhab_conf = {}
					openhab_conf['enabled'] = parser.getboolean('openHAB', 'enabled')
					openhab_conf['authentication'] = parser.getboolean('openHAB', 'authentication')
					openhab_conf['username'] = parser.get('openHAB', 'username')
					openhab_conf['password'] = parser.get('openHAB', 'password')
					openhab_conf['hostname'] = parser.get('openHAB', 'hostname')
					openhab_conf['port'] = int(parser.get('openHAB', 'port'))
					openhab_conf['SSL'] = parser.getboolean('openHAB', 'SSL')
					openhab_conf['item_name'] = parser.get('openHAB', 'item_name')
					logger.debug('MAIN - openhab_conf: {}'.format(openhab_conf))	
				except:
					logger.error('MAIN - Error reading settings from iphonelocation.ini in your [openHAB] section. You may need to start wiith a new .ini \
								 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
								 Exiting!', exc_info = True)
					config_errors == True
			else:
				logger.error('MAIN - You need to have a fully complete [openHAB] section of your current .ini file.')
				config_errors == True

			### Read the iCloud configuration:
			if section_icloudapi == True:
				try:
					### Grab the iCloud API authentication settings:
					icloudapi_conf = {}
					icloudapi_conf['username'] = parser.get('iCloudAPI', 'username')
					icloudapi_conf['password'] = parser.get('iCloudAPI', 'password')
					logger.debug('MAIN - icloudapi_conf: {}'.format(icloudapi_conf))
				except:
					logger.error('MAIN - Error reading settings from iphonelocation.ini in your [iCloudAPI] section. You may need to start wiith a new .ini \
								 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
								 Exiting!', exc_info = True)
					config_errors == True
			else:
				logger.error('MAIN - You need to have a fully complete [iCloudAPI] section of your current .ini file.')
				config_errors == True
		
			### Read the device settings:
			if section_device == True:
				try:
					device_conf = {}
					device_conf['name'] = parser.get('device', 'name')
					device_conf['shortname'] = parser.get('device', 'shortname')
					device_conf['WiFiCheck'] = parser.getboolean('device', 'WiFiCheck')
					device_conf['BTCheck'] = parser.getboolean('device', 'BTCheck')
					device_conf['iCloudGUID'] = parser.get('device', 'iCloudGUID')
					device_conf['location_home_lat'] = parser.get('device', 'location_home_lat')
					device_conf['location_home_long'] = parser.get('device', 'location_home_long')
					logger.debug('MAIN - device_conf: {}'.format(device_conf))
				except:
					logger.error('MAIN - Error reading settings from iphonelocation.ini in your [device] section. You may need to start wiith a new .ini \
								 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
								 Exiting!', exc_info = True)
					config_errors == True
			else:
				logger.error('MAIN - You need to have a fully complete [device] section of your current .ini file.')
				config_errors == True
				
			### Read the general program options:
			if section_general ==True:
				try:
					### Grab general options:
					general_conf = {}
					general_conf['numberofdevices'] = int(parser.get('general', 'numberofdevices'))
					general_conf['cycle_sleep_default'] = float(parser.get('general', 'cycle_sleep_default'))
					general_conf['cycle_sleep_withradio'] = float(parser.get('general', 'cycle_sleep_withradio'))
					general_conf['cycle_sleep_distance'] = float(parser.get('general', 'cycle_sleep_distance'))
					general_conf['cycle_sleep_variable_distance'] = float(parser.get('general', 'cycle_sleep_variable_distance'))
					general_conf['cycle_sleep_variable_modifier_default'] = float(parser.get('general', 'cycle_sleep_variable_modifier_default'))
					general_conf['cycle_sleep_variable_modifier_inbound'] = float(parser.get('general', 'cycle_sleep_variable_modifier_inbound'))
					general_conf['isy_distance_precision'] = int(parser.get('general', 'isy_distance_precision'))
					general_conf['isy_distance_multiplier'] = int(parser.get('general', 'isy_distance_multiplier'))
					general_conf['isold_reject'] = parser.getboolean('general', 'isold_reject')
					general_conf['isold_retries'] = int(parser.get('general', 'isold_retries'))
					general_conf['isold_sleep'] = int(parser.get('general', 'isold_sleep'))	
					general_conf['gpsfromcell_reject'] = parser.getboolean('general', 'gpsfromcell_reject')
					general_conf['gpsfromcell_retries'] = int(parser.get('general', 'gpsfromcell_retries'))
					general_conf['gpsfromcell_sleep'] = int(parser.get('general', 'gpsfromcell_sleep'))	
					general_conf['battery_check'] = parser.getboolean('general', 'battery_check')
					general_conf['battery_threshold'] = int(parser.get('general', 'battery_threshold'))
					general_conf['battery_sleep'] = int(parser.get('general', 'battery_sleep'))		
					general_conf['battery_retries'] = int(parser.get('general', 'battery_retries'))
					general_conf['battery_retries_sleep'] = int(parser.get('general', 'battery_retries_sleep'))
					general_conf['gps_recheck'] = parser.getboolean('general', 'gps_recheck')
					general_conf['gps_recheck_time'] = int(parser.get('general', 'gps_recheck_time'))
					general_conf['battery_isy_reporting'] = parser.getboolean('general', 'battery_isy_reporting')
					general_conf['battery_isy_variable'] = int(parser.get('general', 'battery_isy_variable'))
					logger.debug('MAIN - general_conf: {}'.format(general_conf))
				except:
					logger.error('MAIN - Error reading settings from iphonelocation.ini in your [general] section. You may need to start wiith a new .ini \
								 file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. \
								 Exiting!', exc_info = True)
					config_errors == True
			else:
				logger.error('MAIN - You need to have a fully complete [general] section of your current .ini file.')
				config_errors == True

		### If any configuration errors were found, dump out.
		if config_errors == True:
			logger.error('MAIN - You have configuration errors, please check your .ini file or start with a new one from the iphonelocation.ini.sample file')	
			exit(1)

except:
	logger.error('MAIN - Error reading settings from iphonelocation.ini. You may need to start wiith a new .ini file by copying iphonelocation.ini.sample to iphonelocation.ini and moving all your setting over again. Exiting!', exc_info = True)
	exit(1)

### Connect to MySQL database for logging:
if db_conf['enabled'] == True:
	try:
		db = pw.MySQLDatabase(db_conf['name'], host=db_conf['host'], port=db_conf['port'], user=db_conf['user'], passwd=db_conf['passwd'])
	except:
		logger.error('MAIN - Error connecting to your MySQL database. Please check your database configuration and/or MySQL server.', exc_info=True)
		exit()
#
############################################################################################################
## ENVIRONMENT SETUP                                                                                       #
############################################################################################################
#
### Create the iCloud api object:
global api
api = None
### Create a variable to store the last time the app contacts the iCloud API:
global api_last_used_time
api_last_used_time = None
#
global app_version_running
app_version_running = '0.18.0'
global app_version_current
app_version_current = None
global app_version_check_time
app_version_check_time = None
global app_version_is_current
app_version_is_current = None
global app_version_update_url
app_version_update_url = None

### Create database with proper logging fields:
if db_conf['enabled'] == True:
	class MySQLModel(pw.Model):
		"""A base model that will use our MySQL database"""
		class Meta:
			database = db

	class location_log(MySQLModel):
		iCloud_timeStamp = pw.DateTimeField()
		App_timeStamp = pw.DateTimeField()
		App_data_age = pw.DoubleField()
		App_distance_home = pw.DoubleField()
		iCloud_latitude = pw.DoubleField()
		iCloud_longitude = pw.DoubleField()
		iCloud_horizontalAccuracy = pw.DoubleField()
		iCloud_positionType = pw.CharField()
		iCloud_locationType = pw.CharField()
		iCloud_locationFinished = pw.BooleanField()
		iCloud_isOld = pw.BooleanField()
		iCloud_isInaccurate = pw.BooleanField()
		iCloud_batterylevel = pw.DoubleField()
		App_ISYUpdated = pw.BooleanField()
		App_ISYUpdateValue = pw.DoubleField()
		App_SleepTime = pw.DoubleField()
		App_FailedAttempts = pw.DoubleField()
		App_LoopNumber = pw.DoubleField()
	
	db.connect()
	db.create_tables([location_log], True)
	db.close()
	
	try:
		logger.debug('MAIN - Looking at DB schema')
		db.connect()
	
		### Check to see how many record are in this DB:
		num_of_records = location_log.select().count()
		logger.info('MAIN - There are {} records in the current DB'.format(num_of_records))
		
		if num_of_records == 0:
			logger.info('MAIN - Your DB is empty, dropping and recreating the tables to make sure they are up to date.')
			logger.debug('MAIN - Dropping location_log.')
			db.drop_tables([location_log], True)
			logger.debug('MAIN - Creating location_log.')
			db.create_tables([location_log], True)	
		else:
			try:
				### Try to get a single location log record:
				location_log_data = location_log.get()
				### Print a list of the field names:
				logger.debug('MAIN - The current location_log table has the following fields: {}'.format(location_log_data._data))
				location_log_data = dict(location_log_data._data)
				logger.debug('MAIN - The current location_log dict fields: {}'.format(location_log_data))
				### Print the dict keys:
				logger.debug('MAIN - The current location_log table has the following keys: {}'.format(location_log_data.keys()))
				### Check for battery_level in the DB:
				if 'iCloud_batterylevel' in location_log_data.keys():
					logger.debug('MAIN - iCloud_batterylevel is present in your database')
				else:
					logger.debug('MAIN - iCloud_batterylevel is NOT preset, adding it to your database')
			except:
				logger.warn('MAIN - Getting a record failed, this probably means you do not have the iCloud_batterylevel field in your DB, adding it.', exc_info=True)
				### If getting the record fails, add the battery level field to the DB:
				try:
					logger.debug('MAIN - Definging the migrator')
					migrator = MySQLMigrator(db)
					logger.debug('MAIN - Adding the columnn.')
					#iCloud_batterylevel = pw.DoubleField()
					migrate(
						migrator.add_column('location_log', 'iCloud_batterylevel', pw.DoubleField(default=-1))
					)
				except:
					logger.warn('MAIN - Failed to add the iCloud_batterylevel column', exc_info=True)
		
		db.close()
	except:
		logger.error('MAIN - Looking at DB schema failed!', exc_info=True)
		db.close()
#
#
#
############################################################################################################
## FUNCTION DEFINITIONS                                                                                    #
############################################################################################################
### Fuction that gets and sets ISY variable values:
def isy_variable(action, var_type, var_number, value):
	try:
		logger.debug("ISY_VARIABLE - Running...")
		# Set the ISY username:
		username = isy_conf['username']
		# Set the ISY password:
		password = isy_conf['password']
		# Creates the password manager that will be used to update the ISY:
		passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
		# Creates the authentication function to log in before passing the URL:
		authhandler = urllib2.HTTPBasicAuthHandler(passman)
		logger.debug("ISY_VARIABLE - Set the login parameters for the ISY.")
		
		if var_type == 'integer':
			var_type = 1
		elif var_type == 'state':
			var_type = 2
		else:
			logger.warn("ISY_VARIABLE - No valid variable type supplied, must be 'integer' or 'state'.")
			return 1
		
		logger.debug("ISY_VARIABLE - isy_conf['SSL']: {}".format(isy_conf['SSL']))
		
		if isy_conf['SSL'] == True:
			url_prefix = 'https'
		elif isy_conf['SSL'] == False:
			url_prefix = 'http'
		else:
			logger.warn('ISY_VARIABLE - Could not determine ISY SSL or NOT, assuming HTTP.')
			url_prefix = 'http'
		
		if action == 'get':
			theurl = '{}://{}:{}/rest/vars/{}/{}/{}'.format(url_prefix ,isy_conf['hostname'], isy_conf['port'], action, var_type, var_number)
		elif action == 'set':
			theurl = '{}://{}:{}/rest/vars/{}/{}/{}/{}'.format(url_prefix, isy_conf['hostname'], isy_conf['port'], action, var_type, var_number, value)
		else:
			logger.warn("ISY_VARIABLE - No valid variable action supplied, must be 'get' or 'set'.")
			return 1
		logger.debug('ISY_VARIABLE - The url being used to contact the ISY: {}'.format(theurl))
		# Combine the URL, username and password to be used for access:
		passman.add_password(None, theurl, username, password) #THIS MUST START WITH 'NONE'
		# Create the object to open the URL:
		opener = urllib2.build_opener(authhandler)
		# Set those credentials to be used as the default for all future API calls:
		urllib2.install_opener(opener)
		# Actually open the page to update the ISY:
		pagehandle = urllib2.urlopen(theurl)
		
		if action == 'get':
			#logger.debug("ISY_VARIABLE - pagehandle: {}".format(pagehandle))
			isy_data = pagehandle.read()
			isy_data = xmltodict.parse(isy_data)
			#logger.debug("ISY_VARIABLE - isy_data: {}".format(isy_data))
			#logger.debug("ISY_VARIABLE - isy_data json.jumps: {}".format(json.dumps(isy_data)))
			#logger.debug("ISY_VARIABLE - isy_data json.loads: {}".format( json.loads(json.dumps(isy_data)) ))
			
			isy_data = json.loads(json.dumps(isy_data))
			#logger.debug("ISY_VARIABLE - isy_data: {}".format(isy_data))
			
			isy_data = isy_data['var']
			#logger.debug("ISY_VARIABLE - isy_data: {}".format(isy_data))
			
			isy_data_varvalue = isy_data['val']
			logger.debug("ISY_VARIABLE - isy_data_varvalue: {}".format(isy_data_varvalue))
			
			logger.debug("ISY_VARIABLE - Completed")
			return 0, int(isy_data_varvalue)
		
		if action == 'set':
			#logger.debug("ISY_VARIABLE - pagehandle: {}".format(pagehandle))
			isy_data = pagehandle.read()
			isy_data = xmltodict.parse(isy_data)
			logger.debug("ISY_VARIABLE - isy_data: {}".format(isy_data))
			logger.debug("ISY_VARIABLE - isy_data json.jumps: {}".format(json.dumps(isy_data)))
			logger.debug("ISY_VARIABLE - isy_data json.loads: {}".format( json.loads(json.dumps(isy_data)) ))
			
			isy_data = json.loads(json.dumps(isy_data))
			logger.debug("ISY_VARIABLE - isy_data: {}".format(isy_data))
			
			
			isy_response_status = isy_data['RestResponse']['status']
			logger.debug("ISY_VARIABLE - isy_response_status: {}".format(isy_response_status))
			
			return 0, int(isy_response_status)
		
		logger.debug("ISY_VARIABLE - Completed")
		return 1, -1
	except:
		logger.warn("ISY_VARIABLE - Failed!", exc_info=True)
		return 1, -1
### Fuction that gets and sets ISY variable values:
def openhab(value):
	try:
		logger.debug("OPENHAB - Running...")
		max_attempts = 3
		attempt = 1
		
		while attempt <= max_attempts:
			logger.debug('OPENHAB - Attempt {} of {} to up the openHAB REST API.'.format(attempt, max_attempts))
			### Set the URL protocol type:
			if openhab_conf['SSL'] == True:
				url_prefix = 'https'
			elif openhab_conf['SSL'] == False:
				url_prefix = 'http'
			else:
				logger.warn('OPENHAB - Could not determine ISY SSL or NOT, assuming HTTP.')
				url_prefix = 'http'
			
			### Set the URL appropriately if openHAB authentication is being used.
			if openhab_conf['authentication'] == True:
				#http://localhost:8080/rest/items/SMC_Distance_From_Home/state
				theurl = '{}://{}:{}@{}:{}/rest/items/{}/state'.format(
					url_prefix, openhab_conf['username'], openhab_conf['password'], openhab_conf['hostname'], openhab_conf['port'], openhab_conf['item_name'])
			elif openhab_conf['authentication'] == False:
				theurl = '{}://{}:{}/rest/items/{}/state'.format(
					url_prefix, openhab_conf['hostname'], openhab_conf['port'], openhab_conf['item_name'])
			
			logger.debug('OPENHAB - Sending openHAB a distance of: {}'.format(value))
			
			### Put the data into openHAB
			response = requests.put(theurl,
									data=str(value),
									headers={'content-type':'text/plain'}
									)
			
			logger.debug('OPENHAB - openHAB REST API response status code: {}'.format(response.status_code))
			
			### Check the response status, if it's 202 return, if not retry:
			if response.status_code == 202:
				logger.debug("OPENHAB - Completed")
				return 0
			else:
				logger.debug('OPENHAB - The openHAB REST API did not return a valid response code, retrying.')
				attempt = attempt + 1
		
		logger.warn('OPENHAB - the openHAB REST API was not updated properly in 3 attempts, giving up.')
		return 1
	except:
		logger.warn("OPENHAB - Failed!", exc_info=True)
		return 1


### Fuction to authenticate to the iCloud API:
def api_login():
	try:
		### Make variables global to share data across functions:
		global api
		global api_last_used_time
		
		### Clear any current login data/tokens:
		logger.debug('API_LOGIN - Clearing the current login data.')
		api = None
		
		### Authenticate to the iCloud API and populate the 'api' variable:
		logger.debug('API_LOGIN - Authenticating to the iCloud API.')
		api = PyiCloudService(icloudapi_conf['username'], icloudapi_conf['password'])
		
		### Check to see if they API requested 2 factor authentication:
		if api.requires_2fa:
			twofa_auth()
		else:
			pass
		
		api_last_used_time = datetime.datetime.now()
		logger.debug('API_LOGIN - Sleep for 3 seconds to let login process.')
		time.sleep(3)
	except:
		logger.warn('API_LOGIN - Authentication to iCloud API failed.', exc_info=True)
	return
### Function to print the table header of data to the screen:
def print_table_header():
	### Print the topmost portion of this table header only if there is an update availible.
	if not app_version_is_current and app_version_current != -1:
		logger.info("|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|")
		logger.info("| There is a new version availible, please go to the following URL for release info and to download: {} |".format(app_version_update_url.ljust(68)))
	elif not app_version_is_current and app_version_current == -1:
		logger.info("|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|")
		logger.info("| There was an error checking your application version. For the latest versioning info go to: {} |".format(app_version_update_url.ljust(75)))		
	### Print out an initial table heading:
	logger.info("|---------------------+-------+-------------------+---------------+-----------------+-----------------+---------------+------------+------+-------+-------+-------+-------|")
	logger.info("| Timestamp           |DataAge| DistHome (miles)  | ISY (*Update) | Latitude        | Longitude       | HorizAccuracy |PositionType| Batt |LocType|LocFin | isOld |isInacc|")
	logger.info("|---------------------+-------+-------------------+---------------+-----------------+-----------------+---------------+------------+------+-------+-------+-------+-------|")
### Function to do radio checks for WiFi and Bluetooth:
def individual_radio_check(var, expected_value):
	try:
		logger.debug('INDIVIDUAL_RADIO_CHECK - Running ISY_VARIABLE function.')
		exit_code, returned_value = isy_variable('get', 'state', var, '')
		if exit_code == 0:
			logger.debug('INDIVIDUAL_RADIO_CHECK - ISY_VARIABLE function ran properly.')
			if returned_value == expected_value:
				logger.debug('INDIVIDUAL_RADIO_CHECK - The radio check was true, returning.')
				return 0, True
			elif returned_value != expected_value:
				logger.debug('INDIVIDUAL_RADIO_CHECK - The radio check was False, returning.')
				return 0, False
			if returned_value == expected_value:
				logger.warn('INDIVIDUAL_RADIO_CHECK - The radio check could not determine true or false, retuning with an error.')
				return 1, False
	except:
		logger.error('INDIVIDUAL_RADIO_CHECK - The radio check failed, returning with an error.', exc_info=True)
		return 1, False
### Function to do radio checks:
def radio_check():
	try:
		logger.debug('RADIO_CHECK - Running...')
		
		### Wifi checking:
		if device_conf['WiFiCheck'] == True:
			### Read the value of the wifi present variable:
			logger.debug('RADIO_CHECK - Checking to see if the iPhone is present on WiFi...')
			exit_code, iPhone_WiFi_Here = individual_radio_check(isy_conf['WifiVAR'], isy_conf['WifiVAR_Expected'])
			if exit_code == 0:
				logger.debug("RADIO_CHECK - iPhone_WiFi_Here: {}".format(iPhone_WiFi_Here))
			else:
				iPhone_WiFi_Here = False
				logger.debug("RADIO_CHECK - Reading WiFi value failed, using default value. iPhone_WiFi_Here: {}".format(iPhone_WiFi_Here))
		else:
			iPhone_WiFi_Here = False
			logger.debug('RADIO_CHECK - Script is not set to check for WiFi proximity, continuing...')

		### Bluetooth checking:
		if device_conf['BTCheck'] == True:
			### Read the value of the wifi present variable:
			logger.debug('RADIO_CHECK - Checking to see if the iPhone is present on Bluetooth...')
			exit_code, iPhone_BT_Here = individual_radio_check(isy_conf['BtVAR'], isy_conf['BtVAR_Expected'])
			if exit_code == 0:
				logger.debug("RADIO_CHECK - iPhone_BT_Here: {}".format(iPhone_BT_Here))
			else:
				iPhone_BT_Here = False
				logger.debug("RADIO_CHECK - Reading WiFi value failed, using default value. iPhone_BT_Here: {}".format(iPhone_BT_Here))
		else:
			iPhone_BT_Here = False
			logger.debug('RADIO_CHECK - Script is not set to check for Bluetooth proximity, continuing...')

		
		### Return radio status.
		if iPhone_WiFi_Here or iPhone_BT_Here:
			logger.debug('RADIO_CHECK - the iOS device is in radio range.')
			return True
		else:
			logger.debug('RADIO_CHECK - the iOS device is not in radio range.')
			return False
	except:
		logger.warn('RADIO_CHECK - Failed. Returning False.', exc_info=True)
		return False
### Function to compute sleep time:
def compute_sleep_time(distance_home, distance_home_delta):
	try:
		logger.debug("COMPUTE_SLEEP_TIME - Running...")
		sleep_time = general_conf['cycle_sleep_default']
		# If we're more than the minimum miles away, vary the sleep time based on distance.
		if distance_home > general_conf['cycle_sleep_distance']:
			### If the distance has change more than the sleep variable distance, check if the device is getting closer or farther away:
			if abs(distance_home_delta) > general_conf['cycle_sleep_variable_distance']:
				### If the distance change is positive (getting farther away) use the default sleep time.
				if distance_home_delta > 0:
					logger.debug("COMPUTE_SLEEP_TIME - The distance to home delta is positive, we're getting farther away. Using {} as the sleep modifier.".format(
						general_conf['cycle_sleep_variable_modifier_default']))
					sleep_time = int((distance_home/general_conf['cycle_sleep_variable_modifier_default']) * general_conf['cycle_sleep_default'])
					return 0, sleep_time
				### If the distance change is negative (getting closer) use the modified sleep time.
				elif distance_home_delta < 0:
					logger.debug("COMPUTE_SLEEP_TIME - The distance to home delta is negative, we're getting closer. Using {} as the sleep modifier.".format(
						general_conf['cycle_sleep_variable_modifier_inbound']))
					sleep_time = int((distance_home/general_conf['cycle_sleep_variable_modifier_inbound']) * general_conf['cycle_sleep_default'])
					return 0, sleep_time
				### If we can't tell if we're moving closer or farther away, use the default sleep time.
				else:
					logger.warn("COMPUTE_SLEEP_TIME - The distance to home delta could determine is we're moving closer or farther away. Using {} as the sleep modifier.".format(
						ggeneral_conf['cycle_sleep_default']))
					sleep_time = general_conf['cycle_sleep_default']
					return 0, sleep_time
			else:
				logger.debug("COMPUTE_SLEEP_TIME - We haven't moved more then {}. Using {} as the sleep modifier.".format(
						general_conf['cycle_sleep_variable_distance'], general_conf['cycle_sleep_variable_modifier_default']))
				sleep_time = int((distance_home/general_conf['cycle_sleep_variable_modifier_default']) * general_conf['cycle_sleep_default'])
				return 0, sleep_time
		else:
			### If we're not outside of the minimum distance, use the default sleep time.
			logger.debug("COMPUTE_SLEEP_TIME - We are still inside the minimum distance of {} miles, using the default sleep time of: {}".format(
				general_conf['cycle_sleep_distance'], general_conf['cycle_sleep_default']))
			return 0, sleep_time
	except:
		logger.error("COMPUTE_SLEEP_TIME - Failed!", exc_info=True)
		return 1, 60
### Function to read data from the iCloud API:
def device_data_read():
	try:
		logger.debug('DEVICE_DATA_READ - Running...')
		### Set the attempt number to read data if it's old:
		isold_attempt = 1
		### Set the attempt number to read data if it's old:
		isfromcell_attempt = 1
		
		
		
		while True:
			### Set the isOld pass:
			isold_pass = False
			### Set the isfromcell_pass:
			isfromcell_pass = False
			
			### Read the iCloud API data:
			iPhone_Location = api.devices[device_conf['iCloudGUID']].location()
		
			### If the data returned is "None" log it and return an error:
			if iPhone_Location == None:
				logger.warn('DEVICE_DATA_READ - API data read was "None", returning an error.')
				return 1, 0
		
			### If the data has a latitude and longitude in it continue processing:
			elif 'latitude' in iPhone_Location and 'longitude' in iPhone_Location:
				### Log the data that was read:
				logger.debug('DEVICE_DATA_READ - iPhone Location (all): {}'.format(iPhone_Location))

				### If the app is configured to retry if old data is returned and the "isOld" value is true and we haven't tried too many times, log
				### the warning, increment the attempt number, sleep for the configure seconds and stay in the loop:
				try:
					if general_conf['isold_reject'] == True and iPhone_Location['isOld'] == True and isold_attempt <= general_conf['isold_retries']:
						logger.debug('DEVICE_DATA_READ - Location data from API "isOLD". This is attempt #{}, sleeping for {} seconds and retrying.'.format(
							isold_attempt, general_conf['isold_sleep']))
						isold_attempt = isold_attempt + 1
						time.sleep(general_conf['isold_sleep'])
					### If the app is confgured to reject old data, and the data is old, but we've tried too many times, log the warning and return:
					elif general_conf['isold_reject'] == True and iPhone_Location['isOld'] == True and isold_attempt > general_conf['isold_retries']:
						logger.warn('DEVICE_DATA_READ - Location data from API "isOLD" but we have hit the max retry limit. Continuing.')
						isold_pass = True
					### If the app is confgured to reject old data, but the data isn't old, return it.
					elif general_conf['isold_reject'] == True and iPhone_Location['isOld'] == False:
						logger.debug('DEVICE_DATA_READ - Location data from API is current, continuing.')
						isold_pass = True
					### Is the app is configured to accept old data, and it's old, return it anyway.
					elif general_conf['isold_reject'] == False and iPhone_Location['isOld'] == True:
						logger.debug('DEVICE_DATA_READ - Location data from API "isOLD" but the app is configure to ignore. Continuing.')
						isold_pass = True
					### If the app is configure to accept old data, but this data wasn't old, then just return the good data:
					elif general_conf['isold_reject'] == False and iPhone_Location['isOld'] == False:
						logger.debug('DEVICE_DATA_READ - Location data from API is current, continuing.')
						isold_pass = True
					### If the data doesn't match any of our "isOld" validation conditions, warn us and return anyway:
					else:
						logger.warn('DEVICE_DATA_READ - Location data did not match any "isOld" validation conditions, continuing anyway.')
						isold_pass = True
				except:
					logger.error('DEVICE_DATA_READ - The was as problem with the "isOld" check, it failed!', exc_info=True)

				### If the app is configured to ignore "Cell" based GPS coordinates, sleep for the specified amount of time and max
				### number of retries before returning data anyway
				try:
					if general_conf['gpsfromcell_reject'] == True and iPhone_Location['positionType'] == 'Cell' and isfromcell_attempt <= general_conf['gpsfromcell_retries']:
						logger.debug('DEVICE_DATA_READ - Location data from API was from "Cell", ignoring. This is attempt #{}, sleeping for {} seconds and retrying.'.format(
							isfromcell_attempt, general_conf['gpsfromcell_sleep']))
						isfromcell_attempt = isfromcell_attempt + 1
						time.sleep(general_conf['gpsfromcell_sleep'])
					### If the app is confgured to reject cell data, and the data is from cell, but we've tried too many times, log the warning and return:
					elif general_conf['gpsfromcell_reject'] == True and iPhone_Location['positionType'] == 'Cell' and isfromcell_attempt > general_conf['gpsfromcell_retries']:
						logger.warn('DEVICE_DATA_READ - Location data from API is from "Cell", but we have hit the max retry limit. Continuing.')
						isfromcell_pass = True
					### If the app is confgured to reject cell data, but the data isn't old, return it.
					elif general_conf['gpsfromcell_reject'] == True and iPhone_Location['positionType'] != 'Cell':
						logger.debug('DEVICE_DATA_READ - Location data from API is not from "Cell", continuing.')
						isfromcell_pass = True
					### Is the app is configured to accept cell data, and it's from a cell source, return it anyway.
					elif general_conf['gpsfromcell_reject'] == True and iPhone_Location['positionType'] == 'Cell':
						logger.debug('DEVICE_DATA_READ - Location data from API is from "Cell" but the app is configure to ignore. Continuing.')
						isfromcell_pass = True
					### If the app is configure to accept "Cell" based data, but this data wasn't wasn't from "Cell", then just return the good data:
					elif general_conf['gpsfromcell_reject'] == False and iPhone_Location['positionType'] != 'Cell':
						logger.debug('DEVICE_DATA_READ - Location data from API is not from "Cell", continuing.')
						isfromcell_pass = True
					elif general_conf['gpsfromcell_reject'] == False and iPhone_Location['positionType'] == 'Cell':
						logger.debug('DEVICE_DATA_READ - Location data from API is not from "Cell", continuing.')
						isfromcell_pass = True
					### If the data doesn't match any of our "fromCell" validation conditions, warn us and return anyway:
					else:
						logger.warn('DEVICE_DATA_READ - Location data did not match any "from Cell" validation conditions, continuing anyway.')
						isfromcell_pass = True
				except:
					logger.error('DEVICE_DATA_READ - The was as problem with the "isOld" check, it failed!', exc_info=True)
				
				logger.debug('DEVICE_DATA_READ - The data passed "isOld and "from Cell" validation checks, or hit the max retries, returning data to main function.')	
				### If the data passes the "isOld" and "reject GPS conditions, return it:
				if isold_pass == True and isfromcell_pass == True:
					return 0, iPhone_Location
				else:
					logger.debug('DEVICE_DATA_READ - A data validation check was not passed, retrying.')
					pass
		
			### If the data did not properly pass validation conditions warn us and return anyway.
			else:
				logger.warn('DEVICE_DATA_READ - API data read was not read properly returning an error.')
				return 1, 0
	
	### If something went totally nutso in the data read function, show the traceback info and return an error:
	except:
		logger.debug('DEVICE_DATA_READ - Failed!', exc_info=True)
		return 1, 0
### Fuction to capture 2 factor auth requests:
def twofa_auth():
	try:
		logger.debug('2FA_AUTH - Running...')
		print "Two-factor authentication required. Your trusted devices are:"
	
		devices = api.trusted_devices
		for i, device in enumerate(devices):
			print "  %s: %s" % (i, device.get('deviceName',
				"SMS to %s" % device.get('phoneNumber')))
	
		device = click.prompt('Which device would you like to use?', default=0)
		device = devices[device]
		if not api.send_verification_code(device):
			print "Failed to send verification code"
			sys.exit(1)
		
		code = click.prompt('Please enter validation code')
		if not api.validate_verification_code(device, code):
			print "Failed to verify verification code"
			sys.exit(1)
				
		logger.debug('2FA_AUTH - Completed.')
		return 0
	except:
		logger.debug('2FA_AUTH - Failed!', exc_info=True)
		return 1
### A Function to check battery level:
def device_battery_level():
	try:
		logger.debug('DEVICE_BATTERY_LEVEL - Getting the battery level of the iOS device.')
		retry = 0
		while retry < general_conf['battery_retries']:
			api_battery_level = api.devices[device_conf['iCloudGUID']].status()['batteryLevel']
			logger.debug('DEVICE_BATTERY_LEVEL - api_battery_level: {}'.format(api_battery_level))
		
			### In one shot grab the devices battery level:
			Device_Battery_Level = int(api_battery_level * 100)
			logger.debug('DEVICE_BATTERY_LEVEL - Device_Battery_Level: {}'.format(Device_Battery_Level))
			
			### Validate the data:
			if Device_Battery_Level >= 1 and Device_Battery_Level <= 100:
				logger.debug('DEVICE_BATTERY_LEVEL - Got a valid battery level of: {}%, returning.'.format(Device_Battery_Level))
				if isy_conf['enabled'] == True:
					if general_conf['battery_isy_reporting'] == True:
						logger.debug('DEVICE_BATTERY_LEVEL - Battery level reporting to the ISY is enabled.')
						isy_variable('set', 'state', general_conf['battery_isy_variable'], Device_Battery_Level)
					else:
						logger.debug('DEVICE_BATTERY_LEVEL - Battery level reporting to the ISY is not enabled')
					return 0, Device_Battery_Level
				### The line below was added to be uncommented for testing battery threshold
				#return 0, 15
			else:
				logger.debug('DEVICE_BATTERY_LEVEL - Battery level did not pass validation checks, sleeping for {} seconds and trying again.'.format(general_conf['battery_retries_sleep']))
				time.sleep(general_conf['battery_retries_sleep'])
				retry = retry + 1
		logger.warn('DEVICE_BATTERY_LEVEL - Battery level did not pass validation checks and reach the max number of retries. Continuing without a battery level check.')	
		return 1, 0
	except:
		logger.error('DEVICE_BATTERY_LEVEL - Getting the battery level of the iOS device failed!', exc_info=True)
		return 1, 0
def interval_calc(current, interval, number):
	try:
		#logger.debug('INTERVAL - Running')
		### create a list to store interval numbers:
		intervals = [1]
		interval_count = 1
		while True:
			possible_interval = interval_count * interval
			#logger.debug('INTERVAL - possible_interval: {}'.format(possible_interval))
			if possible_interval <= number:
				intervals.append(possible_interval)
			else:
				break
			interval_count = interval_count + 1
		#logger.debug('INTERVAL - Possible intervals: {}'.format(intervals))
		if current in intervals:
			#logger.debug('INTERVAL - {} is an inverval.'.format(current))
			return True
		else:
			return False
	except:
		logger.warn('INTERVAL - Failed!', exc_info=True)
		return True
def version_check():
	try:
		global app_version_running
		global app_version_current
		global app_version_check_time
		global app_version_is_current
		global app_version_update_url
		### Hit the updates URL to check the most current app version
		logger.debug('VERSION_CHECK - Checking current running version of {} to see if it is the most current.'.format(app_version_running))
		try:
			update_pagehandle = urllib2.urlopen('https://updates.casta.no/aXN5aWNsb3VkcHJveGltaXR5Cg==/master/{}/latest.txt'.format(app_version_running))
			app_version_current = update_pagehandle.read().strip()
		except:
			logger.warn('VERSION_CHECK - Could not connect to or read from the update server. Setting app_version_current to -1')
			app_version_current = -1
		
		### Show the user this version in the debug log
		logger.debug('VERSION_CHECK - The most current version of the application is: {}'.format(app_version_current))
		
		### Set the time this version check was done.
		app_version_check_time = datetime.datetime.now()
		logger.debug('VERSION_CHECK - The last version check was: {}'.format(app_version_check_time))
		
		### Compare the versions to see if they're the seem.
		if app_version_current == app_version_running:
			### Tell the user we're ok and we're on the latest version
			logger.debug('VERSION_CHECK - You are on the latest version.')
			app_version_is_current = True
			return
		else:
			### Tell the user and update is availible.
			logger.debug('VERSION_CHECK - Your current running version does not match the version number of the most current version.')
			app_version_is_current = False
			
			### Grab the current update URL from the updates site:
			try:
				update_pagehandle = urllib2.urlopen('https://updates.casta.no/aXN5aWNsb3VkcHJveGltaXR5Cg==/updateurl.txt')
				app_version_update_url = update_pagehandle.read().strip()
				logger.debug('VERSION_CHECK - You can view the latest releases and grab the new version from: {}'.format(app_version_update_url))
			except:
				logger.debug('VERSION_CHECK - Could not read the update url, setting to default.'.format(app_version_update_url))
				app_version_update_url = 'https://github.com/stevenmcastano/ISY-iCloud-Proximity'
			return
	except:
		logger.warn('VERSION_CHECK - Failed checking for app updates!', exc_info=True)
		app_version_is_current = None
		app_version_update_url = 'Version check failed. This is normal if you are running a dev/non-master release.'
		app_version_check_time = datetime.datetime.now()
		

############################################################################################################
## THREAD DEFINITIONS                                                                                      #
############################################################################################################
#
#
#############################################################################################################
## SCRIPT EXECUTION                                                                                         #
#############################################################################################################
#
### Immediately check the version on startup:
version_check()
### Set this interval to show this is the first time the loop is running:
interval = 1
### Print the table header
print_table_header()
### Initialize the distance to home to show that it's never been read or computed before:			
distance_home_previous = -1
### Initialize the number of attempts it's taken to read data from the api:
failed_attempts = 0
### Connect to the iCloud API:
api_login()
### Initialize the loop number:
loop_number = 0
### Init the distance home previous value:
distance_home_previous = -1
### Init the distance home delta value:
distance_home_delta = 0
### Create a timestamp holder for the last loop run:
last_loop_run = datetime.datetime.now()
### Record the intended loop sleep time:
loop_sleep_time = 0
### Keep track of how many time the loop slept:
loop_sleep_interval = 0
### Run the main script loop:
while True:
	time_since_last_version_check = (((datetime.datetime.now() - app_version_check_time)).total_seconds())/3600
	if time_since_last_version_check >= 6:
		logger.debug('MAIN - It has been {} hours since your last version check, checking again.'.format(time_since_last_version_check))
		version_check()
	
	if loop_sleep_interval >= loop_sleep_time:
		### Record what loop number the application is running
		logger.debug('MAIN - Loop Number: {}'.format(loop_number))
		
		### Calculate the last time the GPS location was read.
		time_since_last_loop_run = ((datetime.datetime.now() - last_loop_run)).total_seconds()
		logger.debug('MAIN - The last iOS device GPS check was {} seconds ago.'.format(time_since_last_loop_run))
	
	### Run the radio check if it hasn't been too long to check the GPS location.
	if general_conf['gps_recheck'] and time_since_last_loop_run >= general_conf['gps_recheck_time']:
		logger.debug('MAIN - It has been too long since the GPS location was read, skipping radio check')
		iPhone_RadioInRange = False
		pass
	elif general_conf['gps_recheck']:
		if loop_sleep_interval >= loop_sleep_time:
			logger.debug('MAIN - The GPS location has been checked recently, running the radio check')
			iPhone_RadioInRange = radio_check()
	else:
		if loop_sleep_interval >= loop_sleep_time:
			logger.debug('MAIN - GPS recheck is not enabled, running the radio check')
			iPhone_RadioInRange = radio_check()
	
	
	### Run the rest of the loop only if the iPhone is out of radio range:
	if not iPhone_RadioInRange:
		logger.debug("MAIN - iPhone is not in radio range or WiFi and BT checking is disabled, checking GPS...")
			
		try:
			### Relogin if the last used time has been over 15 minutes:
			api_token_duration = (datetime.datetime.now() - api_last_used_time).total_seconds()
			if api_token_duration >= 300:
				logger.debug('MAIN - The current API token is {} seconds old, reauthenticating'.format(api_token_duration))
				api_login()
			else:
				logger.debug('MAIN - The current API token is {} seconds old, continuing'.format(api_token_duration))
				
			### Collect the device data
			exit_code, iPhone_Location = device_data_read()
			if exit_code == 0:
				### Set last used time:
				api_last_used_time = datetime.datetime.now()
				### Create a datetime object from the iCloud timeStamp
				iPhone_Location_Time = datetime.datetime.fromtimestamp(iPhone_Location['timeStamp']/1000)
			
				### Create a variable with the lattitude and longitude of the "home" reference point
				location_home = (device_conf['location_home_lat'], device_conf['location_home_long'])
			
				### Create a variable with the lattitude and langitude of the iPhone's current position
				location_phone = (iPhone_Location['latitude'], iPhone_Location['longitude'])
				
				### Determine the distance in miles between the iPhone and "Home"
				distance_home = vincenty(location_home, location_phone).miles
				
				### Always deliver the distance with it's full precision to openHAB
				if openhab_conf['enabled'] == True:
					exit_code = openhab(distance_home)
					if exit_code != 0:
						logger.warn('MAIN - There was an error reporting the distance to openHAB')
					elif exit_code == 0:
						logger.debug('MAIN - openHAB was sent new distance data successfully.')
				else:
					logger.debug('MAIN - openHAB is not enabled.')
			
				### Store the distance to home with precision
				if general_conf['isy_distance_precision'] == 0 and general_conf['isy_distance_multiplier'] == 0:
					logger.debug("MAIN - isy_distance_precision is 0, making the variable an integer.")
					distance_home_precision = int("{:.{}f}".format(distance_home, general_conf['isy_distance_precision']))
				elif general_conf['isy_distance_precision'] == 0 and general_conf['isy_distance_multiplier'] != 0:
					logger.debug("MAIN - isy_distance_precision is 0 but a multiplier is being used")
					distance_home_precision = int(distance_home * general_conf['isy_distance_multiplier'])
				elif general_conf['isy_distance_precision'] != 0 and general_conf['isy_distance_multiplier'] == 0:
					logger.debug("MAIN - isy_distance_precision is being used and the multiplier is 0")
					distance_home_precision = float("{:.{}f}".format(distance_home, general_conf['isy_distance_precision']))
				else:
					logger.warn("MAIN - Both distance precision and multiplier are both set, at least one should be set to '0'")
					distance_home_precision = int(distance_home)
				
				### Determine the change in distance:
				logger.debug("MAIN - ****** distance_home: {}, Type: {}".format(distance_home, type(distance_home)))
				logger.debug("MAIN - ****** distance_home_previous: {}, Type: {}".format(distance_home_previous, type(distance_home_previous)))
				distance_home_delta = distance_home - distance_home_previous
				logger.debug("MAIN - distance_home_delta: {}".format(distance_home_delta))
			
				### Debug output of the iphones location info and it's distance from home.
				logger.debug("MAIN - Location info - Lat: {}, Long: {} (Is Inaccurate: {}, Position Type: {}, Distance From Home: {} miles)".format(
					iPhone_Location['latitude'], iPhone_Location['longitude'], iPhone_Location['isInaccurate'],
					iPhone_Location['positionType'], distance_home))
			
				### Get the battery level if checking is enabled:
				if general_conf['battery_check'] == True:
					### Grab the battery level of the device:
					exit_code, battery_level = device_battery_level()
					if exit_code == 0:
						logger.debug('MAIN - A valid battery level was found. It is: {}%'.format(battery_level))
						battery_level_display = '{}%'.format(battery_level)
					else:
						logger.debug('MAIN - There was an error reading the battery level, ignoring this and moving on.')
						battery_level = -1
						battery_level_display = 'N/A'
				else:
					logger.debug('MAIN - Battery checking is disabled, setting level to -1')
					battery_level = -1
					battery_level_display = 'N/A'
			
				### Show time deltas:
				logger.debug("MAIN - API Timestamp: {}".format(iPhone_Location_Time))
				logger.debug("MAIN - App Timestamp: {}".format(api_last_used_time))
				data_age = (api_last_used_time - iPhone_Location_Time).total_seconds()
				logger.debug("MAIN - Data Age: {} seconds".format(data_age))
				
				if distance_home_previous == distance_home_precision:
					logger.debug("MAIN - The distance from home hasn't changed, moving on.")
					isy_updated = False
					pass
				else:
					logger.debug("MAIN - The distance from home has changed. It was {}, now it's {}, updating the ISY.".format(distance_home_previous, distance_home_precision))
					### Set the following ISY variable
					if isy_conf['enabled'] == True:
						#isy_PX_Steve_Distance_From_Home.value = int(distance_home)
						exit_code, isy_status = isy_variable('set', 'state', isy_conf['DistanceVAR'], distance_home_precision)
						if exit_code != 0 or isy_status != 200:
							logger.warn("MAIN - Updating the ISY failed, will try again next loop.")
							isy_updated = False
						else:
							### Set the previous variable
							isy_updated = True
							logger.debug("MAIN - Recording the distance_home_previous variable.")
							distance_home_previous = distance_home_precision
					
				### Set the ISY value display to reflect if an update was made
				if isy_updated:
					isy_value_string = '{}*'.format(distance_home_precision)
				else:
					isy_value_string = '{}'.format(distance_home_precision)
				
				### Print a line of the table with all needed info regarding the location process
				logger.info("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
							str(iPhone_Location_Time).ljust(19),
							str(int(data_age)).ljust(5),
							str(distance_home).ljust(17),
							str(isy_value_string).ljust(13),
							str(iPhone_Location['latitude']).ljust(15),
							str(iPhone_Location['longitude']).ljust(15),
							str(iPhone_Location['horizontalAccuracy']).ljust(13),
							str(iPhone_Location['positionType']).ljust(10),
							str(battery_level_display).ljust(4),
							str(iPhone_Location['locationType']).ljust(5),
							str(iPhone_Location['locationFinished']).ljust(5),
							str(iPhone_Location['isOld']).ljust(5),
							str(iPhone_Location['isInaccurate']).ljust(5)
							))
				
				### Redisplay the table heading at a certain interval.
				if interval == 0:
					print_table_header()
					### Increase the interval showing we've printed out a line.
					interval = interval + 1
				else:
					### Skip printing the table output and increment the interval.
					interval = interval + 1
					logger.debug('MAIN - Table display interval: {}'.format(interval))
					if interval == 20:
						interval = 0
					else:
						pass
			
			
				### Sleep between checking cycles
				exit_code, sleep_time = compute_sleep_time(distance_home, distance_home_delta)
				if exit_code == 0:
					logger.debug("MAIN - Based on a distance_home of {}, the script wants to sleep for {} seconds.".format(distance_home, sleep_time))
					### Check to see if battery level reading is valid and enabled:
					if general_conf['battery_check'] == True and battery_level != -1:
						logger.debug('MAIN - Battery checking is enabled.')
						if battery_level <= general_conf['battery_threshold']:
							logger.debug('MAIN - Battery level is below the set threshold')
							if sleep_time < general_conf['battery_sleep']:
								logger.debug('MAIN - The computed sleep time is less than the low battery sleep time. Using the low battery sleep time of {} seconds.'.format(general_conf['battery_sleep']))
								sleep_time = general_conf['battery_sleep']
							else:
								logger.debug('MAIN - The computed sleep time is longer than the low battery sleep time. Using the computed sleep time.')
						else:
							logger.debug('MAIN - Battery level is ok, using the computed sleep time.')
							pass
					else:
						logger.debug('MAIN - Battery checking is disabled or there was an error, using computed sleep time.')
						pass
				else:
					logger.debug("MAIN - Computing the sleep time returned an error. Setting it to 300 seconds.")
					sleep_time = 300
	
				if db_conf['enabled'] == True:
					try:
					### Create dict to store data in database:
						db_entry = {
							'iCloud_timeStamp': iPhone_Location_Time,
							'App_timeStamp': api_last_used_time,
							'App_data_age': data_age,
							'App_distance_home': distance_home,
							'iCloud_latitude': iPhone_Location['latitude'],
							'iCloud_longitude': iPhone_Location['longitude'],
							'iCloud_horizontalAccuracy': iPhone_Location['horizontalAccuracy'],
							'iCloud_positionType': iPhone_Location['positionType'],
							'iCloud_locationType': str(iPhone_Location['locationType']),
							'iCloud_locationFinished': iPhone_Location['locationFinished'],
							'iCloud_isOld': iPhone_Location['isOld'],
							'iCloud_isInaccurate': iPhone_Location['isInaccurate'],
							'iCloud_batterylevel': battery_level,
							'App_ISYUpdated': isy_updated,
							'App_ISYUpdateValue': distance_home_precision,
							'App_SleepTime': int(sleep_time),
							'App_FailedAttempts': failed_attempts,
							'App_LoopNumber': loop_number
							}
						db.connect()
						location_log.create(**db_entry)
						db.close()
					except:
						logger.warn('MAIN - DB entry failed.', exc_info = True)
				
				### Reset the number of failed attempts after one works:
				failed_attempts = 0
				
				### Set the current time of completing this iOS read loop:
				last_loop_run = datetime.datetime.now()
				logger.debug('MAIN - last_loop_run: {}, Type: {}'.format(last_loop_run, type(last_loop_run)))
				
				### Sleep
				time.sleep(int(sleep_time))
				
				
			else:
				failed_attempts = failed_attempts + 1
				if failed_attempts < 4:
					logger.warn("MAIN - Reading the iOS device location from API failed! Sleeping for 30 seconds.", exc_info=True)
					time.sleep(30)
					### Reconnect to iCloud service:
					api_login()
				else:
					logger.error("MAIN - Reading the iOS device location from API failed! Max failed attempts reached, restarting the application.", exc_info=True)
					program_restart()	
				
		except:
			logger.error('MAIN - Something in the main script failed! Sleeping for 30 seconds and retrying', exc_info=True)
			time.sleep(30)
	else:
		if loop_sleep_interval >= loop_sleep_time:
			logger.debug("MAIN - iPhone_RadioInRange is {}, sleeping for {} seconds.".format(
				iPhone_RadioInRange, general_conf['cycle_sleep_withradio']))
		else:
			pass
		loop_sleep_time = general_conf['cycle_sleep_withradio']
		time.sleep(1)
		loop_sleep_interval = loop_sleep_interval + 1
		should_i_print = interval_calc(loop_sleep_interval, 60, loop_sleep_time)
		if should_i_print:
			logger.debug('MAIN - I slept for {} of {} intended seconds.'.format(loop_sleep_interval, loop_sleep_time))
		#time.sleep(general_conf['cycle_sleep_withradio'])

		### Increase the loop number showing how many times the checking cycle has run:
		if loop_sleep_interval >= loop_sleep_time:
			loop_sleep_interval = 0
			loop_sleep_time = 0
			loop_number = loop_number + 1
		else:
			pass
	
	### Record the last loop run time:
	#last_loop_run = time.time()
	###### END OF THE WHILE LOOP ######

if opsys == 'linux' or opsys == 'darwin':
	logger.info('MAIN - Removing pidfile: /tmp/{}.pid'.format(application_logging_name))
	os.remove('/tmp/{}.pid'.format(application_logging_name))
elif opsys == 'windows':
	logger.info('MAIN - Removing pidfile: c:\{}.pid'.format(application_logging_name))
	os.remove('c:\{}.pid'.format(application_logging_name))
logger.info('MAIN - Exiting.')
