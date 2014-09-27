#Name: Swap at height
#Info: Swap GCode at a certain height
#Depend: GCode
#Type: postprocess
#Param: swapFilename(string:) gcode path
#Param: swapStartH(float:5.0) Swap start height (mm)
#Param: swapEndH(float:-1.0) Swap end height (mm) (optional)

##The goal of this plugin is to allow user to swap portions of previously saved gcode and generate a new one from it. 
##09/09/2014: Started by Pierre-Marc Simard, pierrem.simard@gmail.com
##09/25/2014: Dirkels: Adding better support for height change. Fixing swap height to locate best matching layer
##09/27/2014: PM: Replaced process of offsetting E value at large in the gcode and added G92 codes instead. This prevent potential max float issues and simplify code. Proposed by GR5

import os, sys, math, re

class gcodeLayerDescriptor():
        RequestedZ = 0.0
        LayerZ = 0.0
        LayerLineIndex = -1
        G0LineIndex = -1
        LayerHeight = 0.0
        LastG1Line = None
        IsFirstLayer = False


#same code as the one in tweak at z plugin. 
def GetValue(line, key, default = None):
        '''
        Find the requested value of key in line or return default value
        '''
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


def SearchForLayerAtZ(requestedZ, lines, swap):
        '''
        Search for the first layer at the requestedZ. 
        return gcodeLayerDescriptor
        '''

        print 'SwapAtZ log: SearchForLayerAtZ(', requestedZ, ', lines)'
        desc = gcodeLayerDescriptor()
        desc.RequestedZ = requestedZ
                
        z = 0.0
        lineIndex = 0
        prePreviousLayerZ = 0.0
        previousLayerZ = 0.0
        layerLineIndex = 0
        lineCount = len(lines)
        lineIndex = 0
        while lineIndex < lineCount:
                if lines[lineIndex].startswith(';LAYER:'):
                        previousLayerLineIndex = layerLineIndex
                        layerLineIndex = lineIndex
                        lineIndex +=1
                        while lineIndex < lineCount:
                                line = lines[lineIndex]
                                if line.startswith('G0'):
                                        z = GetValue(line, "Z", z);
                                        if swap:
                                                if previousLayerZ > requestedZ:
                                                        print 'SwapAtZ log: SearchForLayerAtZ: found at ', previousLayerZ
                                                        desc.LayerZ = previousLayerZ
                                                        desc.LayerLineIndex = previousLayerLineIndex
                                                        desc.G0LineIndex = lineIndex
                                                        desc.LayerHeight = previousLayerZ - prePreviousLayerZ
                                                        desc.LastG1Line = SearchForLastG1Line(lines, desc.LayerLineIndex)
                                                        desc.IsFirstLayer = previousLayerZ == 0.0
                                                        return desc
                                        else:
                                                if z > requestedZ:
                                                        print 'SwapAtZ log: SearchForLayerAtZ: found at ', previousLayerZ
                                                        desc.LayerZ = previousLayerZ
                                                        desc.LayerLineIndex = layerLineIndex
                                                        desc.G0LineIndex = lineIndex
                                                        desc.LayerHeight = previousLayerZ - prePreviousLayerZ
                                                        desc.LastG1Line = SearchForLastG1Line(lines, desc.LayerLineIndex)
                                                        desc.IsFirstLayer = previousLayerZ == 0.0
                                                        return desc

                                        prePreviousLayerZ = previousLayerZ
                                        previousLayerZ = z
                                        break
                                lineIndex +=1

                lineIndex += 1

        return None
        

def CompensateEForLayerHeight(previousLayerZ, desc, lines):
        desiredLayerHeight = desc.LayerZ - previousLayerZ
        if abs(desiredLayerHeight - desc.LayerHeight) > 0.001:
                scaleFactor = desiredLayerHeight / desc.LayerHeight
                
                print 'SwapAtZ log: - Swapped layer require height compensation. previousZ:', previousLayerZ, 'newZ', desc.LayerZ, 'current layer height:', desc.LayerHeight, 'E delta scale factor:', scaleFactor

                lastEValue = -1
                lastModifiedEValue = -1
                ModificationStep = 0
                ConstantDelta = 0.0
                if desc.LastG1Line:
                        lastEValue = GetValue(desc.LastG1Line, "E", -1)
                        lastModifiedEValue = lastEValue

                encounteredLayerCount = 0
                lineCount = len(lines)
                for x in xrange(lineCount):
                        line = lines[x]
                        if line.startswith("G92 ") and "E" in line:
                                if lastEValue != -1:
                                        lastEValue = GetValue(line, "E", -1)
                                        lastModifiedEValue = lastEValue
                                        continue


                        if line.startswith("G1 "):
                                eValue = GetValue(line, "E", -1)
                                if eValue != -1:
                                        if lastEValue == -1:
                                                lastEValue = eValue
                                                lastModifiedEValue = eValue
                                                continue

                                        delta = eValue - lastEValue
                                        lastModifiedEValue = lastModifiedEValue + (delta * scaleFactor)
                                        lastEValue = eValue #we need the lastEValue not modified otherwise we will affect the scaling.
                                        lines[x] = "%sE%0.5f\n" % (line[:line.rfind("E")], lastModifiedEValue)



                        if line.startswith(';LAYER:'):
                                encounteredLayerCount += 1
                                if encounteredLayerCount > 1: #stop scaling and offset E
                                        lines.insert(x, ("G92 E%0.5f\n" % lastEValue))
                                        break
                                        

                        
def ResetE(desc, lines):
        '''
        Add a G92 code to set an offset in the E value for the upcoming layers.
        This remove the need to reset the E values everywhere and avoid potential issues with max float.
        '''
        firstE = -1
        
        if desc.LastG1Line:
                firstE = GetValue(desc.LastG1Line, "E", -1)

        lineCount = len(lines)
        for x in xrange(lineCount):
                line = lines[x]
                if line.startswith("G92 ") and "E" in line:
                        break

                if line.startswith("G1 "):
                        eValue = GetValue(line, "E", -1)
                        if eValue != -1:
                                if firstE == -1:
                                        firstE = eValue

                                lines.insert(x, ("G92 E%0.5f\n" % firstE))
                                break


def SearchForLastG1Line(lines, lineIndex=-1):
        '''
        Start from provided index or end of list and move upward until a G1 command containing an E value is found.
        '''
        if lineIndex == -1 or lineIndex >= len(lines) :
                lineIndex = len(lines)-1
                
        while lineIndex >= 0:
                if lines[lineIndex].startswith("G1 ") and 'E' in lines[lineIndex]:
                        return lines[lineIndex]
                
                lineIndex -= 1

        return None
                

def SplitInSubObjects(lines):
        '''
        split the content of a gcode file into sub objects.
        This allow support for print one at the time option
        '''

        lineCount = len(lines)
        lineIndex = 0
        subObjects = []
        subObjectStart = 0
        for lineIndex in xrange(lineCount):
                if ';Layer count:' in lines[lineIndex]:
                        if subObjectStart != 0:
                                if len(subObjects) == 0:
                                        subObjects.append( lines[:lineIndex-1])
                                else:
                                        subObjects.append( lines[subObjectStart:lineIndex-1])

                        subObjectStart = lineIndex

        if subObjectStart != 0:
                if len(subObjects) == 0:
                        subObjects.append( lines )
                else:
                        subObjects.append( lines[subObjectStart:])

        return subObjects


def SwapContentAtZ(z, currentLines, swapLines, useRetraction=False):
        '''
        Swap content from currentLines with swapLines at given Z and output result of into currentLines
        '''

        #get the descriptor for the given layer. None if not found.
        currentLayerDesc = SearchForLayerAtZ(z, currentLines, False)
        swapTargetDesc = None

        if currentLayerDesc:
                #same but for the swap data but
                #this time we want the layer that come at the same height as the current data
                #because the layer height of current could be bigger than the one of swap data and
                #we dont want to crash layers together. 
                #ex: requested Z = 0.5mm, current data found 0.6mm (layer height 0.2mm) but swap data found 0.5mm (layer height 0.1mm)

                swapTargetDesc = SearchForLayerAtZ(currentLayerDesc.LayerZ, swapLines, True)

        if currentLayerDesc is None or swapTargetDesc is None:
                print 'SwapAtZ log: Cannot swap content for requested z', z, '.CurrentLayer is None:', currentLayerDesc is None, 'SwapTarget is None:', swapTargetDesc is None
                return False

        print 'SwapAtZ log: Swapping content at z', z, 'Layer line index current:', currentLayerDesc.LayerLineIndex, 'swap target:', swapTargetDesc.LayerLineIndex
                

        #If the swap starts somewhere after the first layer we need to perform the following:
        #1. Locate the last G1 line. Currently its always the line before ;LAYER:##.
        #2. Add a G10/G11 (retraction) if needed. distance is bigger than default min retraction (1.5mm) and retraction is present used in print (we dont want to add retraction where there is none desired)
        #3. Compensate the E value for the difference in layer height. If previous layer Z != swap layer Z - swap layer height we need to compensate E.
        #4. Compensate the E value. The issue here is that the new data block contain its own E value based on the amount of filament it extruded already.
        #       Making a swap means we need to tell it where the current file is at in E value.

        del currentLines[currentLayerDesc.LayerLineIndex:]

        swapDataBlock = swapLines[swapTargetDesc.LayerLineIndex:]
        if not currentLayerDesc.IsFirstLayer:
                #step 1. Find the end of the previous layer in the swap content. We need to travel there.
                FirstG1LineIndex = -1
                FirstG1EValue = -1
                for lineIndex in xrange(len(swapDataBlock)):
                        if swapDataBlock[lineIndex].startswith('G1 ') and 'E' in swapDataBlock[lineIndex]:
                                FirstG1EValue = GetValue(swapDataBlock[lineIndex], 'E', -1)
                                FirstG1LineIndex = lineIndex
                                break


                if currentLayerDesc.LastG1Line and useRetraction and FirstG1LineIndex != -1:

                        #step 2. Retraction codes
                        xG1 = GetValue(currentLayerDesc.LastG1Line, 'X', None)
                        yG1 = GetValue(currentLayerDesc.LastG1Line, 'Y', None)
                        xG0 = GetValue(swapLines[swapTargetDesc.G0LineIndex], 'X', None)
                        yG0 = GetValue(swapLines[swapTargetDesc.G0LineIndex], 'Y', None)

                        if xG1 and yG1 and xG0 and yG0:
                                x = xG1 - xG0
                                y = yG1 - yG0
                                dist = math.sqrt(x*x + y*y)
                                if dist > 1.5: #default retraction distance
                                        print 'SwapAtZ log: - Adding retraction between layers. Distance', dist, ' > 1.5mm'

                                        swapDataBlock.insert(FirstG1LineIndex, 'G11\n')
                                        swapDataBlock.insert(0, 'G10\n')
                                        FirstG1LineIndex += 2
                                        
                                        
                #step 3. Check layer height
                CompensateEForLayerHeight(currentLayerDesc.LayerZ, swapTargetDesc, swapDataBlock)

                #step 4. Get current E value
                ResetE(swapTargetDesc, swapDataBlock)
                
        #add the swap content
        currentLines.append(';SwapAtZ Start for requested Z%s\n' % z)
        currentLines += swapDataBlock

        return True


print 'SwapAtZ log: ==========================================='
                        
if os.path.exists(swapFilename):

        print 'SwapAtZ log: Target file exist.'

        #get the current content
        with open(filename, "r") as f:
                currentLines = f.readlines()

        #get the content that we want to swap in
        with open(swapFilename, "r") as f:
                swapLines = f.readlines()

        #define if we use retraction in this gcode or not.
        useRetraction = False
        for l in currentLines:
                if "G11" in l: #end retraction (G10 is start retraction and occur at the end of the print)
                        useRetraction = True
                        break
                        
        if not useRetraction:
                for l in swapLines:
                        if "G11" in l: #end retraction (G10 is start retraction and occur at the end of the print)
                                useRetraction = True
                                break


        #split the content in sub objects. Allow support for print one at a time mode and ease the swapping process.
        currentLinesSubObjects = SplitInSubObjects(currentLines)
        swapLinesSubObjects = SplitInSubObjects(swapLines)
                
        print 'SwapAtZ log: SubObjectSplits current:', len(currentLinesSubObjects), 'target:',len(swapLinesSubObjects)

        #make sure they constain the same number of objects
        if len(currentLinesSubObjects) == len(swapLinesSubObjects):

                lines = []
                totalEValue = 0

                for subObjectIndex in xrange(len(currentLinesSubObjects)):
                        subObjectLines = currentLinesSubObjects[subObjectIndex][:]

                        print 'SwapAtZ log: Checking sub object', subObjectIndex

                        #swap the content from the current with the desired gcode content until the end of the subobject.
                        if SwapContentAtZ(swapStartH, subObjectLines, swapLinesSubObjects[subObjectIndex], useRetraction):

                                #if the swap end before the end.
                                if swapEndH > swapStartH:
                                        #swap content back to current gcode content.
                                        SwapContentAtZ(swapEndH, subObjectLines, currentLinesSubObjects[subObjectIndex], useRetraction)

        
                        layerIndex = 0
                        lineCount = len(subObjectLines)

                        #reset layer numbers
                        for x in xrange(lineCount):
                
                                if subObjectLines[x].startswith(";LAYER:"):
                                        subObjectLines[x] = ";LAYER: %i\n" % layerIndex
                                        layerIndex += 1

                        #get last E value and add it to the total for material count
                        x = lineCount-1
                        while x >= 0:
                                if subObjectLines[x].startswith("G1 ") and 'E' in subObjectLines[x]:
                                        totalEValue += GetValue(subObjectLines[x], "E", -1)
                                        break

                                x -= 1


                        #set the layer count
                        for x in xrange(lineCount):
                                if subObjectLines[x].startswith(";Layer count:"):
                                        subObjectLines[x] = ";Layer count: %i\n" % (layerIndex + 1)
                                        break
                        
                        print 'SwapAtZ log: - new layer count', layerIndex + 1
                
                        lines += subObjectLines

                #set the material count
                if totalEValue > 0:
                        print 'SwapAtZ log: new Material value', totalEValue
                        for x in xrange(lineCount):
                                if lines[x].startswith(";MATERIAL:"):
                                        lines[x] = ";MATERIAL: %i\n" % totalEValue
                                        break

                #write the result back
                with open(filename, "w") as f:
                        for line in lines:
                                f.write(line)

        else:
                print 'SwapAtZ log: Cannot perform swap when not the same number of objects are printed one at a time'


else:
        print 'SwapAtZ log: Target file does not exist.'


print 'SwapAtZ log: ==========================================='