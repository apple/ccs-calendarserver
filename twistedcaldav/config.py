##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

__all__ = [
    "Config",
    "ConfigDict",
    "ConfigProvider",
    "ConfigurationError",
    "config",
]

import os
import copy

class ConfigurationError(RuntimeError):
    """
    Invalid server configuration.
    """

class ConfigDict(dict):
    """
    Dictionary which can be accessed using attribute syntax, because
    that reads an writes nicer in code.  For example:
      C{config.Thingo.Tiny.Tweak}
    instead of:
      C{config.["Thingo"]["Tiny"]["Tweak"]}
    """
    def __init__(self, mapping=None):
        if mapping is not None:
            for key, value in mapping.iteritems():
                self[key] = value

    def __repr__(self):
        return "*" + dict.__repr__(self)

    def __setitem__(self, key, value):
        if key.startswith("_"):
            # Names beginning with "_" are reserved for real attributes
            raise KeyError("Keys may not begin with '_': %s" % (key,))

        if isinstance(value, dict) and not isinstance(value, self.__class__):
            dict.__setitem__(self, key, self.__class__(value))
        else:
            dict.__setitem__(self, key, value)

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            dict.__setattr__(self, attr, value)
        else:
            self[attr] = value

    def __getattr__(self, attr):
        if not attr.startswith("_") and attr in self:
            return self[attr]
        else:
            return dict.__getattribute__(self, attr)

    def __delattr__(self, attr):
        if not attr.startswith("_") and attr in self:
            del self[attr]
        else:
            dict.__delattr__(self, attr)

class ConfigProvider(object):
    """Configuration provider, abstraction for config storage/format/defaults"""

    def __init__(self, defaults=None):
        """Create configuration provider with given defaults"""
        self._configFileName = None
        if defaults is None:
            self._defaults = ConfigDict()
        else:
            self._defaults = ConfigDict(copy.deepcopy(defaults))
            
    def getDefaults(self):
        """Return defaults"""
        return self._defaults
    
    def setDefaults(self, defaults):
        """Change defaults"""
        self._defaults = ConfigDict(copy.deepcopy(defaults))
    
    def getConfigFileName(self):
        """Return current configuration file path+name"""
        return self._configFileName
    
    def setConfigFileName(self, configFileName):
        """Change configuration file path+name for next load operations"""
        self._configFileName = configFileName
        if self._configFileName:
            self._configFileName = os.path.abspath(configFileName)
    
    def hasErrors(self):
        """Return true if last load operation encountered any errors"""
        return False
            
    def loadConfig(self):
        """Load the configuration, return a dictionary of settings"""
        return self._defaults
    

class Config(object):

    def __init__(self, provider=None):
        if not provider:
            self._provider = ConfigProvider()
        else:
            self._provider = provider
        self._preUpdateHooks = set()
        self._postUpdateHooks = set()
        self.reset()
        
    def __setattr__(self, attr, value):
        if "_data" in self.__dict__ and attr in self.__dict__["_data"]:
            self._data[attr] = value
        else:
            self.__dict__[attr] = value

    def __getattr__(self, attr):
        if attr in self._data:
            return self._data[attr]
        raise AttributeError(attr)

    def __hasattr__(self, attr):
        return attr in self._data
    
    def __str__(self):
        return str(self._data)

    def get(self, attr, defaultValue):
        parts = attr.split(".")
        lastDict = self._data
        for part in parts[:-1]:
            if not part in lastDict:
                lastDict[attr] = ConfigDict()
            lastDict = lastDict.__getattr__(part)
        configItem = parts[-1]
        if configItem in lastDict:
            return lastDict[configItem]
        else:
            lastDict[configItem] = defaultValue
            return defaultValue

    def getInt(self, attr, defaultValue):
        return int(self.get(attr, defaultValue))

    def addPreUpdateHook(self, hook):
        if isinstance(hook, list) or isinstance(hook, tuple):
            self._preUpdateHooks.update(hook)
        else:
            self._preUpdateHooks.add(hook)
        
    def addPostUpdateHook(self, hook):
        if isinstance(hook, list) or isinstance(hook, tuple):
            self._postUpdateHooks.update(hook)
        else:
            self._postUpdateHooks.add(hook)

    def getProvider(self):
        return self._provider
    
    def setProvider(self, provider):
        self._provider = provider
        self.reset()

    def setDefaults(self, defaults):
        self._provider.setDefaults(defaults)
        self.reset()

    def updateDefaults(self, items):
        _mergeData(self._provider.getDefaults(), items)
        self.update(items)

    def update(self, items):
        if not isinstance(items, ConfigDict):
            items = ConfigDict(items)
        # Call hooks
        for hook in self._preUpdateHooks:
            hook(self._data, items)
        _mergeData(self._data, items)
        for hook in self._postUpdateHooks:
            hook(self._data)

    def load(self, configFile):
        self._provider.setConfigFileName(configFile)
        configDict = ConfigDict(self._provider.loadConfig())
        if not self._provider.hasErrors():
            self.update(configDict)
        else:
            raise ConfigurationError("Invalid configuration in %s"
                % (self._provider.getConfigFileName(), ))

    def reload(self):
        configDict = ConfigDict(self._provider.loadConfig())
        configDict._reloading = True
        if not self._provider.hasErrors():
            self.reset()
            self.update(configDict)
        else:
            raise ConfigurationError("Invalid configuration in %s"
                % (self._provider.getConfigFileName(), ))

    def reset(self):
        self._data = ConfigDict(copy.deepcopy(self._provider.getDefaults()))


def _mergeData(oldData, newData):
    for key, value in newData.iteritems():
        if isinstance(value, (dict,)):
            if key in oldData:
                assert isinstance(oldData[key], ConfigDict), \
                    "%r in %r is not a ConfigDict" % (oldData[key], oldData)
            else:
                oldData[key] = {}
            _mergeData(oldData[key], value)
        else:
            oldData[key] = value

config = Config()
