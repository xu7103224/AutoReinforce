# coding=utf-8

import configparser
import os
import sys
import zipfile
import subprocess
import logging
import dexparser
import struct
import xmlparser
import elfparser
import shutil

logging.basicConfig(level=logging.INFO,  
                    format = "%(asctime)s [%(levelname)s] %(message)s",  
                    datefmt = '%Y-%m-%d %H:%M') 


def encryptDex(originDex, encryptedDex):
    inDex = open(originDex, "rb")
    outDex = open(encryptedDex, "wb+")
    while True:
        byte = inDex.read(1)
        if not byte:
            break
        value = (~int.from_bytes(byte, byteorder='little')) & 0x00ff
        outDex.write(struct.pack("B", value))
    inDex.close()
    outDex.close()

def unzip(apk):
    parentDir = os.path.abspath(os.path.join(apk, os.pardir))
    unzipPath = os.path.join(parentDir, "tmp", "decompress")
    if os.path.isdir(unzipPath):
        pass
    else:
        os.makedirs(unzipPath)
    zipFile = zipfile.ZipFile(apk)
    for names in zipFile.namelist():
        zipFile.extract(names, unzipPath)
    zipFile.close()
    logging.info("apk decompressed completed")
    return unzipPath

def decompile(apk):
    parentDir = os.path.abspath(os.path.join(apk, os.pardir))
    decompilePath = os.path.join(parentDir, "tmp", "decompile")
    if os.path.isdir(decompilePath):
        pass
    else:
        os.makedirs(decompilePath)
    apktool = os.path.join(os.getcwd(), "tools", "apktool_2.3.3.jar")
    cmd = "java -jar " + apktool + " d -f " + apk + " -o " + decompilePath
    ret = subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ret == 0:
        logging.info("apk decompiled completed")
    else:
        logging.info("apk decompiled failed")
        sys.exit()
    return decompilePath

def repack(apk):
    parentDir = os.path.abspath(os.path.join(apk, os.pardir))
    workDir = os.path.abspath(os.path.join(parentDir, os.pardir))
    outPath = os.path.join(workDir, "output")
    if os.path.isdir(outPath):
        pass
    else:
        os.makedirs(outPath)
    apktool = os.path.join(os.getcwd(), "tools", "apktool_2.3.3.jar")
    newapk = os.path.join(outPath, "new.apk")
    cmd = "java -jar " + apktool + " b " + apk + " -o " + newapk
    ret = subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ret == 0:
        logging.info("apk repcked completed")
    else:
        logging.error("apk repacked failed")
        sys.exit()
    return newapk

def signAndInstall(newapk):
    signapk = os.path.join(os.getcwd(), "tools", "signapk.jar")
    pk = os.path.join(os.getcwd(), "tools", "testkey.pk8")
    pem = os.path.join(os.getcwd(), "tools", "testkey.x509.pem")
    parentDir = os.path.abspath(os.path.join(newapk, os.pardir))
    signedapk = os.path.join(parentDir, "signed.apk")
    cmd = "java -jar " + signapk + " " + pem + " " + pk + " " + newapk + " " + signedapk
    ret = subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    cmd = "adb install -t -r " + signedapk
    logging.info("apk signed completed")
    ret = subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ret == 0:
        logging.info("apk installed completed")
    else:
        logging.error("apk installed failed")
        sys.exit()

def ndk_build():
    currentDir = os.getcwd()
    ndkDir = os.path.join(currentDir, "core")
    os.chdir(ndkDir)
    cmd = "ndk-build"
    ret = subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    os.chdir(currentDir)
    if ret == 0:
        logging.info("ndk-build completed")
    else:
        logging.error("ndk-build failed")
        sys.exit()
        

def main():
    #读取配置文件
    config = configparser.ConfigParser()
    config.read("config.ini")
    sections = config.sections()
    encryptedInfo = ""
    apkPath = config["Application"]["app"]
    funNum = config["Application"]["num"]
    if not os.path.exists(apkPath):
        logging.error("cannot find apk file")
        sys.exit(1)
    workDir = os.path.abspath(os.path.join(apkPath, os.pardir))

    #解压APK
    decompressPath = unzip(apkPath)

    #反编译APK
    decompilePath = decompile(apkPath)
    
    #将待加密函数native化
    dexPath = os.path.join(decompressPath, "classes.dex")
    dex = dexparser.Dex(dexPath)
    logging.info("classes.dex parsing completed")
    encryptedInfo += funNum
    for i in range(int(funNum)):
        cname = config["FUNCTION" + str(i)]["class"]
        fname = config["FUNCTION" + str(i)]["function"]
        sig = config["FUNCTION" + str(i)]["signature"]
        codeoff = dex.java2native(cname, fname, sig)
        encryptedInfo = encryptedInfo + cname + fname + sig + str(codeoff)
    dex.update_signature()
    dex.update_checksum()
    dex.save()
    logging.info("classes.dex modified completed")

    #将修改后的dex文件加密，打包为protected.jar
    assetsPath = os.path.join(decompilePath, "assets")
    if os.path.isdir(assetsPath):
        pass
    else:
        os.makedirs(assetsPath)
    encryptedDexPath = os.path.join(assetsPath, "protected.jar")
    encryptDex(dexPath, encryptedDexPath)
    logging.info("classes.dex encrypted completed")

    #修改原app的manifest
    manifest = xmlparser.xml(os.path.join(workDir, "tmp", "decompile", "AndroidManifest.xml"))
    manifest.add_application("com.example.shellapplication.WrapperApplication")
    manifest.save()
    logging.info("AndroidManifest.xml modified completed")

    #将tmp/decompile/smali 替换为 factory/smali
    shutil.rmtree(os.path.join(decompilePath, "smali"))
    shutil.copytree(os.path.join(os.getcwd(), "factory", "smali"), os.path.join(decompilePath, "smali"))

    #将加密函数信息写入data.h, 并重新编译libcore.so
    data_h = open(os.path.join(os.getcwd(), "core", "jni", "data.h"), "w")
    data_h.write("char encryptedData[] = \"")
    for i in encryptedInfo:
        data_h.write("\\x%x" % (ord(i) - 10))
    data_h.write("\";")
    data_h.close()
    ndk_build()
    
    #对so进行加固
    elf = elfparser.Elf(os.path.join(os.getcwd(), "core", "libs", "armeabi-v7a", "libloader.so"))
    elf.insert_so(os.path.join(os.getcwd(), "core", "libs", "armeabi-v7a", "libcore.so"))
    #将core/libs/ 移动到 tmp/decompile/lib
    libPath = os.path.join(decompilePath, "lib", "armeabi-v7a")
    if not os.path.isdir(libPath):
        os.makedirs(libPath)
    elf.save()
    shutil.copy(os.path.join(os.getcwd(), "core", "libs", "armeabi-v7a", "libreinforce.so"), libPath) 
    #shutil.copy(os.path.join(os.getcwd(), "core", "libs", "armeabi-v7a", "libcore.so"), libPath) 

    #重打包apk
    newapk = repack(decompilePath)
    
    #sign and install apk
    signAndInstall(newapk)
    


if __name__ == "__main__":
    main()
