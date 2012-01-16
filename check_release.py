# coding: utf8
'''
   Copyright [2012] Yumemi Inc.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.


Created on 2012/01/12

@author: mokemokechicken on Twitter

How To Use:
    python check_release.py <root_path> [<exclude_class_list_filename>]
    
        root_path: root directory of the source codes to find .m, .mm, .h files recursively.
        exclude_class_list_filename: filename of "Don't Check This Class" list. In the file, Write ONE Class name in ONE Line.

Specification:
    This program find that retained or copied properties those seem not to be released in Objective-C.
    The result will output to stdout.
    You should remember that it is NOT perfect. (^^;
    
    It supposed that:

    * "Property declaration" is written in @interface - @end block.

    * Property declaration may be written in .h, .m, .mm files.

    * "Release description" is written in @implemantation - @end block of .m or .mm files.
    
    * Property declaration is 'ONE property is in ONE line', like:
        
        @property (nonatomic, retain) NSNumber *userId;
        @property (nonatomic, retain) NSNumber *score;
        
        NOT
        
        @property (nonatomic, retain) NSNumber *userId, *score;
    
    
    * Syntax of release description of 'myName' property is like:
        
        self.myName = nil;
        
        or
        
        [myName release] or [_myName release] or [myName_ release]    (autorelease is also OK)
        
        or
        
        [self setMyName:nil];
    
    * The place of release description is not checked whether it will be executed when dealloc is called.
'''

import os
import glob
import re
import sys


root_path = len(sys.argv) > 1 and sys.argv[1]
exclude_class_list_filename = len(sys.argv) > 2 and sys.argv[2]

class ReleaseChecker(object):
    TARGET_RE = re.compile(r"\.(m|h|mm)$")
    # 
    INTERFACE_NAME_RE = re.compile(r"^\s*@interface\s*([a-zA-Z0-9_]+)")
    IMPLEMENTATION_NAME_RE = re.compile(r"^\s*@implementation\s*([a-zA-Z0-9_]+)")
    END_BLOCK_RE = re.compile(r"^\s*@end\s*")
    #
    PROPERTY_LINE_RE = re.compile(r"^\s*@property\s*\([^)]+\)")
    PROPERTY_RETAIN_LINE_RE = re.compile(r"^\s*@property\s*\([^)]*(?:retain|copy)[^)]*\)")
    PROPERTY_NAME_RE = re.compile(r"[\s*]\s*([a-zA-Z0-9_]+)\s*;")
    PROPERTY_BLOCK_NAME_RE = re.compile(r"^\s*@property\s*\([^)]+\)[^(]+\(\s*\^\s*([a-zA-Z0-9_]+)\)")
    SELFNIL_NAME_RE = re.compile(r"(?:^|;)\s*self\.([a-zA-Z0-9_]+)\s*=\s*nil\s*;")
    SETTERNIL_NAME_RE = re.compile(r"(?:^|;)\s*\[\s*self\s*set([a-zA-Z0-9_]+)\s*:\s*nil\s*\]")
    RELEASE_NAME_RE = re.compile(r"(?:^|;)\s*\[\s*([a-zA-Z0-9_]+)\s+(?:release|autorelease)\s*\]")
    #
    RETAIN_FLG = 1
    ASSING_FLG = 2
    SELFNIL_FLG = 4

    def check_start(self, root_path, exclude_class_list_filename=None):
        """Start Main Logic"""
        self.repo = {}
        self.ex_list = set()
        if exclude_class_list_filename:
            self.load_exclude_class_list(exclude_class_list_filename)
        self.check_dir(root_path)
        self.check_result()
    
    def load_exclude_class_list(self, exclude_class_list_filename):
        """Load Uncheck Class Info"""
        fin = open(exclude_class_list_filename)
        for line in fin:
            line = line.strip()
            if not line or line[0] == "#":
                continue
            self.ex_list.add(line)
        fin.close()
    
    def check_dir(self, target_dir):
        for path in glob.glob("%s/*" % target_dir):
            if os.path.isdir(path):
                self.check_dir(path)
            else:
                self.check_file(path)
    
    def check_file(self, path):
        if not self.TARGET_RE.search(path):
            return
        base, ext = os.path.splitext(os.path.basename(path))
        if ext == ".h":
            self.find_retain(path)
        elif ext == ".m" or ext == ".mm":
            self.find_retain(path)
            self.find_release(path)

    def find_retain(self, path):
        """Find 'retain' or 'copy' descriptions in a file"""
        fin = open(path, "r")
        base = None
        for line in fin:
            ################ DECIDE Class SCOPE
            iname =  self.INTERFACE_NAME_RE.findall(line) or self.IMPLEMENTATION_NAME_RE.findall(line)
            if len(iname) == 1:
                base = iname[0]
            if self.END_BLOCK_RE.search(line):
                base = None
            if not base or base in self.ex_list:
                continue
            ################ Find Property Declaration
            if not self.PROPERTY_LINE_RE.search(line):
                continue
            is_retain = self.PROPERTY_RETAIN_LINE_RE.search(line) != None
            matches = self.PROPERTY_NAME_RE.findall(line)
            if len(matches) != 1:
                matches = self.PROPERTY_BLOCK_NAME_RE.findall(line)
                if len(matches) != 1:
                    self.log("WARNING LINE: %s" % line)
                    continue
            pname = matches[0]
            ################# Store Property Info
            properties = self.repo.get(base, {})
            flg = self.RETAIN_FLG if is_retain else self.ASSING_FLG
            properties[pname] = properties.get(pname, 0) | flg
            self.repo[base] = properties
        fin.close()

    def find_release(self, path):
        """Find 'release' description in a file"""
        fin = open(path, "r")
        base = None
        for line in fin:
            ################ DECIDE Class SCOPE
            iname =  self.INTERFACE_NAME_RE.findall(line) or self.IMPLEMENTATION_NAME_RE.findall(line)
            if len(iname) == 1:
                base = iname[0]
            if self.END_BLOCK_RE.search(line):
                base = None
            if not base or base in self.ex_list:
                continue
            ################ find property release descriptions
            matches = self.SELFNIL_NAME_RE.findall(line) or self.RELEASE_NAME_RE.findall(line)
            match_by_setter = False
            if len(matches) == 0:
                matches = self.SETTERNIL_NAME_RE.findall(line)
                if len(matches) == 0:
                    continue
                match_by_setter = True
            ################ Store Property Info
            properties = self.repo.get(base, {})
            for pname in matches:
                if match_by_setter: # MyName -> myName
                    pname = pname[0].lower() + pname[1:]
                if pname[0] == "_": # _myName -> myName
                    pname = pname[1:]
                if pname[-1] == "_": # myName_ -> myName
                    pname = pname[:-1]
                properties[pname] = properties.get(pname, 0) | self.SELFNIL_FLG
            self.repo[base] = properties
        fin.close()

    def check_result(self):
        """show result"""
        for base in sorted(self.repo.keys()):
            properties = self.repo[base]
            if base is None:
                self.log("=" * 30 + " base is None!")
                self.log(properties)
            for pname in properties:
                if properties[pname] == self.RETAIN_FLG:
                    self.log("ETYPE1: %s: [%s] is not released?" % (base, pname))
                elif properties[pname] == self.SELFNIL_FLG:
                    #self.log("ETYPE2: %s: [%s] is only released" % (base, pname))
                    pass
                elif properties[pname] not in (self.ASSING_FLG, self.RETAIN_FLG | self.SELFNIL_FLG, self.ASSING_FLG | self.SELFNIL_FLG):
                    self.log("ETYPEx: %s: [%s] (%s)????" % (base, pname, properties[pname]))

    def log(self, message):
        print message

if __name__ == '__main__':
    if not root_path:
        print "Usage: %s <root_path> [<exclude_class_list_filename>]" % os.path.basename(__file__)
        sys.exit(1)
    rc = ReleaseChecker()
    rc.check_start(root_path, exclude_class_list_filename)
