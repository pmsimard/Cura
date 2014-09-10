#Name: Swap at height
#Info: Swap GCode at a certain height
#Depend: GCode
#Type: postprocess
#Param: swapFilename(string:) gcode path
#Param: swapStartH(float:5.0) Swap start height (mm)
#Param: swapEndH(float:-1.0) Swap end height (mm) (optional)

##The goal of this plugin is to allow user to swap portions of previously saved gcode and generate a new one from it. 
##Writen by Pierre-Marc Simard, pierrem.simard@gmail.com


import re
import os

def getValue(line, key, default = None):
	if not key in line or (';' in line and line.find(key) > line.find(';')):
		return default
	subPart = line[line.find(key) + 1:]
	m = re.search('^[0-9]+\.?[0-9]*', subPart)
	if m is None:
		return default
	try:
		return float(m.group(0))
	except:
		return default


def searchForZ(lines, z0, z1):

        zState = 0
        z0Index = 0
        z1Index = -1

        z = 0.0
        lineIndex = 0
        for line in lines:
                if line.startswith('G0') and lines[lineIndex-1].startswith(';LAYER:'):
                        z = getValue(line, "Z", z);
                        if zState == 0 and z >= z0:
                                zState = 1
                                z0Index = lineIndex
                                if z1 <= 0.0:
                                        break

                        elif zState == 1 and z >= z1:
                                z1Index = lineIndex
                                break
                                

                lineIndex += 1

        return (z0Index, z1Index)

def searchForLastG1Line(lines, lineIndex=-1):

        if lineIndex == -1:
                lineIndex = len(lines)-1
                
        while lineIndex >= 0:
                if lines[lineIndex].startswith("G1 ") and getValue(lines[lineIndex], "E", -1) != -1:
                        return lines[lineIndex]
                
                lineIndex -= 1

        return None
                
def ResetE(lines, value):
        if value == -1:
                return

        firstE = -1
        delta = -1
        
        lineCount = len(lines)
        for x in xrange(lineCount):
                line = lines[x]
                if line.startswith("G1 ") and getValue(line, "E", -1) != -1:
                        curE = getValue(line, "E", -1)

                        if firstE == -1:
                                firstE = curE
                                delta = firstE - value
                                curE = value

                        else:
                                curE -= delta

                        lines[x] = "%sE%0.5f\n" % (lines[x][:lines[x].rfind("E")], curE)
                

if os.path.exists(swapFilename):

        #get the current content
        with open(filename, "r") as f:
                currentLines = f.readlines()

        #get the content that we want to swap in
        with open(swapFilename, "r") as f:
                swapLines = f.readlines()
                
        #find where the swap start and end in the current data. -1 means end of file
        swapStart, swapEnd = searchForZ(currentLines, swapStartH, swapEndH)

        #same but for the swap data
        swapTargetStart, swapTargetEnd = searchForZ(swapLines, swapStartH, swapEndH)

        with open("swapAtZ.log", "w") as logf:
                logf.write(filename + "->" + swapFilename + "\n")
                logf.write("Code Chunks:%i, %i, %i, %i\n" % (swapStart, swapEnd, swapTargetStart, swapTargetEnd))

        #this is the resulting gcode file containing the swap of content.
        lines = []

        #start. Take the begining of the file and keep it.
        if swapStart > 0:
                lines = currentLines[0:swapStart-1]

        #swap section. Get the section from swaplines that needs to be put in. From swat target start to the target end.
        swapLinesSet = swapLines[swapTargetStart-1:] if swapTargetEnd == -1 else swapLines[swapTargetStart-1:swapTargetEnd-1]

        #If the swap starts somewhere after the first layer we need to perform the following:
        #1. Locate the last G1 line. Currently its always the line before ;LAYER:##.
        #2. Add a G0 code to navigate the same point as that G1 at a given speed. Speed should be TravelSpeed. For now its print speed.
        #3. Compensate the E value. The issue here is that the swapLineSet contain its own E value based on the amount of filament it extruded already.
        #       Making a swap means we need to tell it where the current file is at.
        if swapStartH != 0:
                #step 1. Find the end of the previous layer in the swap content. We need to travel there.
                G1Line = searchForLastG1Line(swapLines, swapTargetStart-1)
                if G1Line:
                        #step 2. Travel to that location
                        lines.append("G0 F%i X%0.2f Y%0.2f\n" % (getValue(G1Line, "F", 3000), getValue(G1Line, "X", 100.0), getValue(G1Line, "Y", 100.0)))
                else:
                        raise Exception("Cannot find any G1 line in swapLines starting at " + str(swapTargetStart) + ". Find something for this case")
                
                #step 3. Get current E value
                CurrentG1Line = searchForLastG1Line(lines)
                if CurrentG1Line:
                        #make the E value of the swap content match the one of the current data
                        ResetE(swapLinesSet, getValue(CurrentG1Line, "E", -1))

                else:
                        raise Exception("Cannot compensate the E value of the swaped content. GCode will not be valid")

        #add the swap content
        lines += swapLinesSet
        
        #If the swap did not cover the remaining of the file. We need to do the same 3 steps as above.
        if swapEnd != -1:
                currentLineSet = currentLines[swapEnd-1:]

                #step 1. Find the end of the previous layer in the current content. We need to travel there.
                G1Line = searchForLastG1Line(currentLines, swapEnd-1)
                if G1Line:
                        #step 2. Travel to that location
                        lines.append("G0 F%i X%0.2f Y%0.2f\n" % (getValue(G1Line, "F", 3000), getValue(G1Line, "X", 100.0), getValue(G1Line, "Y", 100.0)))
                else:
                        raise Exception("Cannot find any G1 line in currentLines starting at " + str(swapTargetStart) + ". Find something for this case")


                #step 3. Get current E value
                CurrentG1Line = searchForLastG1Line(lines)
                if CurrentG1Line:
                        #make the E value of the swap content match the one of the current data
                        ResetE(currentLineSet, getValue(CurrentG1Line, "E", -1))
                        
                lines += currentLineSet

        lastEValue = -1
        layerIndex = 0
        lineCount = len(lines)

        #reset layer numbers
        for x in xrange(lineCount):
                
                if lines[x].startswith(";LAYER:"):
                        lines[x] = ";LAYER:" + str(layerIndex) + "\n"
                        layerIndex += 1

        #get last E value and 
        x = lineCount-1
        while x >= 0:
                if lines[x].startswith("G1 ") and getValue(lines[x], "E", -1) != -1:
                        lastEValue = getValue(lines[x], "E", -1)
                        break

                x -= 1

        #set the layer count
        for x in xrange(lineCount):
                if lines[x].startswith(";Layer count:"):
                        lines[x] = ";Layer count: " + str(layerIndex + 1) + "\n"
                        break
                        
        #set the material count
        if lastEValue != -1:
                for x in xrange(lineCount):
                        if lines[x].startswith(";MATERIAL:"):
                                lines[x] = ";MATERIAL: " + str(int(lastEValue)) + "\n"
                                break

        with open(filename, "w") as f:
                for line in lines:
                        f.write(line)
