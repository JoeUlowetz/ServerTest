#!/usr/bin/python3
# common.py

from ioutils.misc import get_data_subpath
import time
import datetime
import os
#from ioutils.camera_api_constants import *     # this provides camera error constants and helper funcs
import subprocess

# ??? MAYBE PUT log_event IN HERE AS WELL????


def build_image_filename(pycam_info, user_obj):

    flavor_suffix = ""
    try:
        api = user_obj['API']
        if api == "API_EXAMINE_PLATEN_PAGE":      # 1010
            flavor_suffix = "__A"
        elif api == "API_CHECK_PLATEN_PUNCH":     # 1012
            flavor_suffix = "__B"
        elif api == "API_EXAMINE_OUTFEED_PAGE":   # 1011
            flavor_suffix = ""      # don't use for outfeed images
        else:
            flavor_suffix = "__M"  # menu used to take an image
        # Why these letters? Because Examine/Punch images follow each other, so a/b in filenames; others will
        # be by themselves, so to tell them apart give then next letter.
    except:
        pass

    local_path = get_data_subpath("camera")

    # use "ts1" as timestamp for filename, unless it is unreasonably old, in which case use current timestamp
    now = datetime.datetime.fromtimestamp(user_obj["ts1"])
    raw_time = user_obj["ts1"]
    yesterday = time.time() - 86400
    tomorrow = time.time() + 86400
    if raw_time < yesterday or raw_time > tomorrow:
        print("Unreasonable value ts1")
        now = datetime.datetime.now()
    datestamp = now.strftime("%Y-%m-%d")

    if 'build_id' in user_obj and isinstance(user_obj['build_id'],int):
        build_id_str = "Build_%d" % user_obj['build_id']
    else:
        build_id_str = "General"

    if 'page_num' in user_obj and isinstance(user_obj['page_num'],int):
        page_str = "pg-%04d" % user_obj['page_num']
        timestamp = now.strftime("__%H-%M-%S")
    else:
        page_str = ''
        timestamp = now.strftime("%H-%M-%S")

    image_suffix = pycam_info.image_format

    filename = "%s%s%s.%s" % (page_str, timestamp, flavor_suffix, image_suffix)
    full_name = os.path.join(local_path, build_id_str, datestamp,  pycam_info.camera_name, filename)

    return full_name


def build_rpi_info(detail):
    """
    :param detail:   see below (default=3) (everything=63) (disable=0)
    :return: return dictionary of items that are appended to return_user_obj in response network message

    Note: detail & 1 is for Outfeed camera thread info; that is handled elsewhere

    if detail & 2
        disk_usage = string     # from: df -h
        uptime = string         # from: uptime
    if detail & 4
        cpu_temp = string       # from: vcgencmd measure_temp
        top = string            # from: top -1 -b
    if detail & 8
        debian = string         # from: cat /etc/debian (version of Debian running)
        release = string        # from: cat /etc/os-release (OS release notes)
        kernal = string         # from: uname -a
    if detail & 16
        processes = string      # from: ps -ef
    if detail & 32
        watchdog_count = number  # from: wc -l /home/pi/ImpossibleObjects/watchdog/watchdog.log
        watchdog_recent = number # from: tail -5 /home/pi/ImpossibleObjects/watchdog/watchdog.log
    """
    info_dict = {}

    if detail & 2:
        bash_cmd = ["df","-h"]
        process = subprocess.Popen(bash_cmd, stdout=subprocess.PIPE)
        output, error = process.communicate()
        info_dict["disk_usage"] = output.decode("utf-8")

        bash_cmd = ["uptime",]
        process = subprocess.Popen(bash_cmd, stdout=subprocess.PIPE)
        output, error = process.communicate()
        info_dict["uptime"] = output.decode("utf-8")

    if detail & 4:
        # This is how many times the watchdog timer has restarted; this includes power-up as well as reboot cmds
        # It can be watched over time to see how often the watchdog runs. Note that the watchdog can be triggered
        # to reboot the RPi via GPIO signal. (It is also possible to reboot the RPi using a network message from
        # the client; however this is not recorded as a watchdog event.) In the future the hardware will be able
        # to power cycle the RPi to insure it reboots, but this is in the future.
        bash_cmd = ["wc","-l","/home/pi/ImpossibleObjects/watchdog/watchdog.log"]
        process = subprocess.Popen(bash_cmd, stdout=subprocess.PIPE)
        output, error = process.communicate()
        num_value = -999    # flag in case of problem
        if len(output) > 0:
            tup = output.split(' ')     # return string looks like: '47 watchdog.log'
            value = tup[0]
            if type(value) == int:
                num_value = int(value)
        info_dict["watchdog_count"] = num_value

        # This lists the five most recent times the watchdog restarted
        bash_cmd = ["tail","-5","/home/pi/ImpossibleObjects/watchdog/watchdog.log"]
        process = subprocess.Popen(bash_cmd, stdout=subprocess.PIPE)
        output, error = process.communicate()
        info_dict["watchdog_recent"] = output.decode("utf-8")

    if detail & 8:
        bash_cmd = ["vcgencmd", "measure_temp"]
        process = subprocess.Popen(bash_cmd, stdout=subprocess.PIPE)
        output, error = process.communicate()
        info_dict["cpu_temp"] = output.decode("utf-8")

        bash_cmd = ["top","-n", "1", "-b"]
        process = subprocess.Popen(bash_cmd, stdout=subprocess.PIPE)
        output, error = process.communicate()
        info_dict["top"] = output.decode("utf-8")

    if detail & 16:
        bash_cmd = ["cat","/etc/debian"]
        process = subprocess.Popen(bash_cmd, stdout=subprocess.PIPE)
        output, error = process.communicate()
        info_dict["debian"] = output.decode("utf-8")

        bash_cmd = ["cat","/etc/os-release"]
        process = subprocess.Popen(bash_cmd, stdout=subprocess.PIPE)
        output, error = process.communicate()
        info_dict["release"] = output.decode("utf-8")

        bash_cmd = ["uname","-a"]
        process = subprocess.Popen(bash_cmd, stdout=subprocess.PIPE)
        output, error = process.communicate()
        info_dict["kernal"] = output.decode("utf-8")

    if detail & 32:
        bash_cmd = ["ps","-ef"]
        process = subprocess.Popen(bash_cmd, stdout=subprocess.PIPE)
        output, error = process.communicate()
        info_dict["processes"] = output.decode("utf-8")

    return info_dict