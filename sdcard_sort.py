#This was tested on a Windows 7 pc and is intended to be used with the UM2.
#Recursively move the content back and fort in temp folders in order to force the content to be sorted on the FAT.
#If the script fail look for any remaining temp folders in the sub folders and look for moved files.
#This way the content appear sorted when browsing on the UM2 led screen.

#Written by Pierre-Marc Simard, pierrem.simard@gmail.com


import os
import tempfile


#Edit root folder to change start sorting location
root = r'I:\\'



def SortContent(folder):
    print "sorting content for", folder
    content = os.listdir(folder)
    tempdir = tempfile.mkdtemp(dir=folder)

    content.sort()
    for f in content:
        realPath = os.path.join(folder, f)
        if os.path.isdir(realPath):
            tempPath = os.path.join(tempdir, f)
            try:
                os.rename(realPath, tempPath)
                os.rename(tempPath, realPath)
            except:
                print "ERROR: Folder could not be sorted", realPath, tempPath
            
    for f in content:
        realPath = os.path.join(folder, f)
        if not os.path.isdir(realPath):
            tempPath = os.path.join(tempdir, f)
            try:
                os.rename(realPath, tempPath)
                os.rename(tempPath, realPath)
            except:
                print "ERROR: File could not be sorted", realPath, tempPath
                
    for f in content:
        realPath = os.path.join(folder, f)
        if os.path.isdir(realPath):
            SortContent(realPath)

    os.rmdir(tempdir)
    

SortContent(root)
