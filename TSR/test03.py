# -*- coding: UTF-8 -*-

from __future__ import print_function
import os, io, sys, json, time, platform, urlparse, traceback, re
import subprocess
import multiprocessing as mp
import threading
import zipfile
import ftplib
import getpass
import ConfigParser
import paho.mqtt.client as mqtt
from gevent import socket
from urllib2 import Request, urlopen, URLError, HTTPError
from urllib import urlencode, quote
from colorama import Fore, Back, Style
from colorama import init

init()  # for colorama


# SETTINGS
########################################################################################
class Setting:
    def __init__(self):
        self.ip = '192.168.2.2'
        self.am_ip = '192.168.2.1'
        self.cs_ip = '192.168.51.100'
        self.socket_port = 3187
        self.test_case = []
        self.program_dir = "C:\\Test\\"
        self.result_dir = ""
        self.tsr_revision = '2.0'
        self.ftp_account = 'AM001'
        self.ftp_password = '123456'
        self.env_file = 'env.txt'
        self.mqtt_sub = 'ARCI/CS-RPi/001/CMD'
        self.mqtt_pub = 'ARCI/RPi-CS/001/CMD'


# SETTINGS
########################################################################################
MQTT_MSG = ''
TEST_NAME = ['',
             'HDD - Stress - IO Meter - Data Transfer 511906.6 X02',
             'R09c Data Access with S3&S4 Interruption X12']

########################################################################################
def show_setting(s):
    print(Fore.YELLOW + '# Setting')
    print(Fore.WHITE + '  IP        : ' + Fore.GREEN + s.ip)
    print(Fore.WHITE + '  RPi-IP    : ' + Fore.GREEN + s.am_ip)
    print(Fore.WHITE + '  CS-IP     : ' + Fore.GREEN + s.cs_ip)
    print(Fore.WHITE + '  PORT      : ' + Fore.GREEN + str(s.socket_port))
    print(Fore.WHITE + '  PROGRAM   : ' + Fore.GREEN + s.program_dir)
    print(Fore.WHITE + '  RESULT    : ' + Fore.GREEN + s.result_dir)
    print(Fore.WHITE + '  MQTT-SUB  : ' + Fore.GREEN + s.mqtt_sub)
    print(Fore.WHITE + '  MQTT-PUB  : ' + Fore.GREEN + s.mqtt_pub)


########################################################################################
def zip_file(src, dest=""):
    """
    input : Folder path and name
    output: using zipfile to ZIP folder
    """
    cwd = os.path.dirname(os.path.abspath(__file__))  # os.getcwd()

    try:
        if (dest == ""):
            zf = zipfile.ZipFile(src + '.zip', mode='w')
        else:
            zf = zipfile.ZipFile(dest, mode='w')

        os.chdir(src)

        for root, folders, files in os.walk(".\\"):
            for sfile in files:
                aFile = os.path.join(root, sfile)
                zf.write(aFile)
        zf.close()
    finally:
        os.chdir(cwd)


def unzip_file(src):
    file_name = os.path.basename(src)
    file_path = os.path.abspath(os.path.dirname(src))
    # print(Fore.WHITE + '  ' + file_path + file_name)
    try:
        zip_ref = zipfile.ZipFile(src, 'r')
        zip_ref.extractall(file_path)
        zip_ref.close()
    except zip_ref.BadZipfile as ex:
        print(Fore.RED + ex)


########################################################################################
def set_env_file(env_file):
    env_os = platform.platform()
    env_cpu = platform.processor()[0:platform.processor().find(' ')]
    env_arch = platform.architecture()[0]
    env_name = platform.node()
    # ----------------------------------------------------------------------------------#
    print(Fore.YELLOW + '# Environment')
    print(Fore.WHITE + '  OS        : ' + Fore.GREEN + env_os)
    print(Fore.WHITE + '  CPU       : ' + Fore.GREEN + env_cpu)
    print(Fore.WHITE + '  ARCH      : ' + Fore.GREEN + env_arch)
    print(Fore.WHITE + '  NAME      : ' + Fore.GREEN + env_name)
    # ----------------------------------------------------------------------------------#
    json_env = str(json.dumps
        ({
        'PLATFORM': env_name,
        'OS': env_os,
        'ARCH': env_arch,
        'CPU': env_cpu
    }))
    # print ('  JSON: ' + jsonENV)
    # ----------------------------------------------------------------------------------#
    savFile = os.path.dirname(os.path.abspath(__file__)) + '\\' + env_file
    print(Fore.WHITE + '  Save as ' + savFile, end='')
    envFile = open(savFile, 'w')
    envFile.write(json_env)
    envFile.close()
    print(Fore.CYAN + '  ok')


########################################################################################
def ftp_upload(serv, usr, pwd, src):
    print(Fore.WHITE + '  Connect ' + serv + ' ...', end='')
    ftp = ftplib.FTP(serv)
    ftp.login(usr, pwd)
    cwd = os.path.dirname(os.path.abspath(__file__))
    file_name = os.path.basename(src)
    file_path = os.path.abspath(os.path.dirname(src))
    os.chdir(file_path)
    with open(file_name, 'rb') as contents:
        print(Fore.CYAN + '  ok')
        print(Fore.WHITE + '  Upload ...', end='')
        ftp.storbinary('STOR %s' % file_name, contents)
    ftp.quit()
    os.chdir(cwd)
    print(Fore.CYAN + '  ok')

########################################################################################
def http_download(url):
    file_name = url.split('/')[-1]
    url = 'http://' + quote(url)
    u = urlopen(url)
    f = open(file_name, 'wb')
    meta = u.info()
    file_size = int(meta.getheaders("Content-Length")[0])
    print(Fore.WHITE + "  File: %s Bytes: %s" % (file_name, file_size))

    file_size_dl = 0
    block_sz = 8192
    while True:
        buffer = u.read(block_sz)
        if not buffer:
            break

        file_size_dl += len(buffer)
        f.write(buffer)
        status = "  Progress: %10d  [%3.2f%%]" % (file_size_dl, file_size_dl * 100. / file_size)
        status = status + chr(8) * (len(status) + 1)
        print(status, end="\r")
    print('                                                                 ', end="\r")
    f.close()


########################################################################################
def mqtt_get_msg(client, userdata, message):
    global MQTT_MSG
    MQTT_MSG = str(message.payload.decode("utf-8"))
    # print("received message =", str(message.payload.decode("utf-8")))


########################################################################################
def download_job_file(srv, dest, job):
    ret = ""
    url = srv + '/dispatcher/file/'
    cwd = os.path.dirname(os.path.abspath(__file__))

    os.chdir(dest)

    for task in job:
        while True:
            print(Fore.WHITE + '  Download ' + url + TEST_NAME[int(task)] + '.zip')
            try:
                http_download(url + TEST_NAME[int(task)] + '.zip')
                break
            except:
                print(Fore.RED + '  Download Fail, Retry...' + Fore.WHITE)
                pass

    os.chdir(cwd)


########################################################################################
def chk_socket(am_ip, socket_port):
    retry_num = 0
    retry_max = 10000
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    while True:
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((am_ip, socket_port))
        except:
            print(Fore.RED + '  err: client_socket.connect fail(' + str(retry_num) + ')' + Fore.WHITE)
            if retry_num < retry_max:
                retry_num = retry_num + 1
                time.sleep(3)
                pass
            else:
                raise
        else:
            retry_num = 0
            while True:
                try:
                    client_socket.send('t')
                    time.sleep(1)
                except:
                    if retry_num < retry_max:
                        print(Fore.RED  + '  err: client_socket.send fail(' + str(retry_num) + ')' + Fore.WHITE)
                        time.sleep(1)
                        retry_num = retry_num + 1
                        pass
                    else: 
                        retry_num = 0
                        client_socket.close()
                        break
########################################################################################
def deleteFile(path):
    file=os.listdir(path)
    os.system("rd /S /Q C:\\Test")
    #os.remove("%s" % path+i)
    print("  OK")
########################################################################################
def main():
    # ----------------------------------------------------------------------------------#
    # Get Default Setting
    # ----------------------------------------------------------------------------------#
    setting = Setting()
    setting.result_dir = 'C:\\Users\\' + getpass.getuser() + '\\Desktop\\Test\\'
    print(Fore.WHITE + '================================================================')
    print(Fore.WHITE + '|                       TSR Version  ' + setting.tsr_revision + '                       |')
    print(Fore.WHITE + '================================================================')
    show_setting(setting)
    # ----------------------------------------------------------------------------------#
    # Link Socket
    # ----------------------------------------------------------------------------------#
    print(Fore.YELLOW + '# Init Socket')
    print(Fore.WHITE + '  Connect ' + setting.am_ip + ':' + str(setting.socket_port) + ' ...', end='')
    client_socket = mp.Process(target=chk_socket, args=(setting.am_ip, setting.socket_port))
    client_socket.start()
    print(Fore.CYAN + '  ok')
    # ----------------------------------------------------------------------------------#
    # Init MQTT
    # ----------------------------------------------------------------------------------#
    print(Fore.YELLOW + '# Init MQTT')
    print(Fore.WHITE + '  Connect ' + setting.cs_ip + ':1883' + ' ...', end='')
    mqtt_client = mqtt.Client()
    mqtt_client.connect(setting.cs_ip, 1883)
    mqtt_client.subscribe(setting.mqtt_sub)
    mqtt_client.on_message = mqtt_get_msg
    print(Fore.CYAN + '  ok')
    mqtt_client.loop_start()
    # mqtt_client.loop_forever()
    print(Fore.WHITE + '  Sub Topic: ' + setting.mqtt_sub)
    print(Fore.WHITE + '  Pub Topic: ' + setting.mqtt_pub)
    # ----------------------------------------------------------------------------------#
    # Get Environment Information
    # ----------------------------------------------------------------------------------#
    set_env_file(setting.env_file)
    ftp_upload(setting.cs_ip, setting.ftp_account, setting.ftp_password, setting.env_file)
    mqtt_client.publish(setting.mqtt_pub, '[UPDENV]')
    # ----------------------------------------------------------------------------------#
    # Remove old test files
    # ----------------------------------------------------------------------------------#
    print(Fore.BLUE + '  Remove old test files ...')
    deleteFile("C:\\Test\\")
    # time.sleep(10)
    ''' -------------------------------------------------------------------------------
    waiting for [JOB:xx,xx,xx]
    ------------------------------------------------------------------------------- '''
    while True:
        print(Fore.YELLOW + '# Job')
        print(Fore.WHITE + '  Waiting for Command ...')
        job = []
        while True:
            m = re.search('\[JOB:(.+?)]', MQTT_MSG)
            if m:
                print(Fore.WHITE + '  Get CMD: ' + Fore.GREEN + MQTT_MSG)
                job = m.group(1).split(',')  # each cut ','
                print(Fore.WHITE + '  Job List:' + str(job))
                break
        os.system("md C:\\Test")
        download_job_file(setting.cs_ip, setting.program_dir, job)
        mqtt_client.publish(setting.mqtt_pub, '[READY]')

        for task in job:
            '''print(Fore.BLUE + '  Remove old test files ...')
            try:
                os.system("del /f /S /Q C:\\Test\\* > null 2>&1")
                os.remove("null")
                print("  OK")
            except:
                pass'''
            print(Fore.BLUE + '  Waiting for Kick Off ...')
            while True:
                if MQTT_MSG == '[KICKOFF]':
                    break
            print(Fore.YELLOW + '# Task: ' + task)
            mqtt_client.publish(setting.mqtt_pub, '[GO:' + task + ']')
            task_zip = setting.program_dir + TEST_NAME[int(task)] + '.zip'
            print(Fore.WHITE + '  Unzip File ' + task_zip)
            unzip_file(task_zip)
            print(Fore.WHITE + '  Testing ...' + setting.program_dir + TEST_NAME[
                int(task)] + '\AutoTestTool\Windows10X64\Run.exe')
            '''subprocess.call([setting.program_dir + TEST_NAME[int(task)] + '\AutoTestTool\Windows10X64\Run.exe'],
                            shell=False)'''
            result = ConfigParser.ConfigParser()
            result.read(setting.result_dir + TEST_NAME[int(task)] + "\\TestStatus.ini")
            print(Fore.WHITE + '  Test Result: ', end='')
            if result.get(TEST_NAME[int(task)], 'Status') == 'Finish':
                result = 0
                print(Fore.GREEN + 'PASS')
            else:
                result = 1
                print(Fore.RED + 'FAIL')
            # zip file log file
            print(Fore.WHITE + '  ZIP Report File')
            report = setting.result_dir + TEST_NAME[int(task)]
            report_time =report + time.strftime("-%Y%m%d", time.localtime())
            zip_file(report,report_time + '.zip')
            time.sleep(3)
            print(Fore.WHITE + '  Upload Report File')
            ftp_upload(setting.cs_ip, setting.ftp_account, setting.ftp_password, report_time + ".zip")
            mqtt_client.publish(setting.mqtt_pub, '[DONE:' + str(result) + ']')

        mqtt_client.publish(setting.mqtt_pub, '[END]')
        # print('')
        print(Fore.WHITE + '  Job Finish')

    client_socket.close()
    mqtt_client.loop_stop()


########################################################################################
if __name__ == "__main__":
    print(Style.RESET_ALL)
    main()
    print(Style.RESET_ALL)
