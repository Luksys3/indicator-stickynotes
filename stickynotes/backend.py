# Copyright © 2012-2015 Umang Varma <umang.me@gmail.com>
#
# This file is part of indicator-stickynotes.
#
# indicator-stickynotes is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# indicator-stickynotes is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along with
# indicator-stickynotes.  If not, see <http://www.gnu.org/licenses/>.

from datetime import datetime
import uuid
import json
import urllib.request
from os.path import expanduser
import threading, time

from stickynotes.info import FALLBACK_PROPERTIES, HTTP_MONITOR_DEFAUTLS

class Note:
    def __init__(self, content=None, gui_class=None, noteset=None,
            category=None):
        self.gui_class = gui_class
        self.noteset = noteset
        content = content or {}
        self.uuid = content.get('uuid')
        self.body = content.get('body', '')
        self.properties = content.get("properties", {})
        self.http_monitor_settings = content.get("http_monitor_settings", HTTP_MONITOR_DEFAUTLS)
        self.http_monitor_updater = HTTPMonitorUpdater(self,
            self.http_monitor_settings['address'],
            self.http_monitor_settings['updateInterval'])
        self.category = category or content.get("cat", "")
        if not self.category in self.noteset.categories:
            self.category = ""
        last_modified = content.get('last_modified')
        if last_modified:
            self.last_modified = datetime.strptime(last_modified,
                    "%Y-%m-%dT%H:%M:%S")
        else:
            self.last_modified = datetime.now()
        # Don't create GUI until show is called
        self.gui = None

    def extract(self):
        if not self.uuid:
            self.uuid = str(uuid.uuid4())
        if self.gui != None:
            self.gui.update_note()
            self.properties = self.gui.properties()
        return {"uuid":self.uuid, "body":self.body,
                "last_modified":self.last_modified.strftime(
                    "%Y-%m-%dT%H:%M:%S"), "properties":self.properties,
                "cat": self.category,
                "http_monitor_settings": self.http_monitor_settings}

    def update(self, body=None):
        if not body == None:
            self.body = body
            self.last_modified = datetime.now()

    def delete(self):
        self.noteset.notes.remove(self)
        self.noteset.save()
        del self

    def show(self, *args, **kwargs):
        # If GUI has not been created, create it now
        if self.gui == None:
            self.gui = self.gui_class(note=self)
        else:
            self.gui.show(*args, **kwargs)

    def hide(self):
        if self.gui != None:
            self.gui.hide()

    def set_locked_state(self, locked):
        # if gui hasn't been initialized, just change the property
        if self.gui == None:
            self.properties["locked"] = locked
        else:
            self.gui.set_locked_state(locked)

    def set_http_monitor_state(self, state):
        # if gui hasn't been initialized, just change the property
        if self.gui == None:
            self.properties["http_monitor_state"] = state
        else:
            self.gui.set_http_monitor_state(state)

    def set_http_monitor_settings(self, settings):
        for attr, value in settings.items():
            self.http_monitor_settings[attr] = value
        self.http_monitor_updater.set_address(self.http_monitor_settings["address"])
        self.http_monitor_updater.set_update_interval(self.http_monitor_settings["updateInterval"])

    def start_http_monitor(self):
        self.http_monitor_updater.start()
        # self.http_monitor_updater = HTTPMonitorUpdater(self,
        #     self.http_monitor_settings['address'],
        #     self.http_monitor_settings['updateInterval'])

    def stop_http_monitor(self):
        self.http_monitor_updater.stop()
        # self.http_monitor_updater = HTTPMonitorUpdater(self,
        #     self.http_monitor_settings['address'],
        #     self.http_monitor_settings['updateInterval'])

    def cat_prop(self, prop):
        """Gets a property of the note's category"""
        return self.noteset.get_category_property(self.category, prop)


class NoteSet:
    def __init__(self, gui_class, data_file, indicator):
        self.notes = []
        self.properties = {}
        self.categories = {}
        self.gui_class = gui_class
        self.data_file = data_file
        self.indicator = indicator

    def _loads_updater(self, dnoteset):
        """Parses old versions of the Notes structure and updates them"""
        return dnoteset

    def loads(self, snoteset):
        """Loads notes into their respective objects"""
        notes = self._loads_updater(json.loads(snoteset))
        self.properties = notes.get("properties", {})
        self.categories = notes.get("categories", {})
        self.notes = [Note(note, gui_class=self.gui_class, noteset=self)
                for note in notes.get("notes",[])]

    def dumps(self):
        return json.dumps({"notes":[x.extract() for x in self.notes],
            "properties": self.properties, "categories": self.categories})

    def save(self, path=''):
        output = self.dumps()
        with open(path or expanduser(self.data_file),
                mode='w', encoding='utf-8') as fsock:
            fsock.write(output)

    def open(self, path=''):
        with open(path or expanduser(self.data_file),
                encoding='utf-8') as fsock:
            self.loads(fsock.read())

    def load_fresh(self):
        """Load empty data"""
        self.loads('{}')
        self.new()

    def merge(self, data):
        """Update notes based on new data"""
        jdata = self._loads_updater(json.loads(data))
        self.hideall()
        # update categories
        if "categories" in jdata:
            self.categories.update(jdata["categories"])
        # make a dictionary of notes so we can modify existing notes
        dnotes = {n.uuid : n for n in self.notes}
        for newnote in jdata.get("notes", []):
            if "uuid" in newnote and newnote["uuid"] in dnotes:
                # Update notes that are already in the noteset
                orignote = dnotes[newnote["uuid"]]
                if "body" in newnote:
                    orignote.body = newnote["body"]
                if "properties" in newnote:
                    orignote.properties = newnote["properties"]
                if "cat" in newnote:
                    orignote.category = newnote["cat"]
            else:
                # otherwise create a new note
                if "uuid" in newnote:
                    uuid = newnote["uuid"]
                else:
                    uuid = str(uuid.uuid4())
                dnotes[uuid] = Note(newnote, gui_class=self.gui_class,
                        noteset=self)
        # copy notes over from dictionary to list
        self.notes = list(dnotes.values())
        self.showall(reload_from_backend=True)

    def new(self):
        """Creates a new note and adds it to the note set"""
        note = Note(gui_class=self.gui_class, noteset=self,
                category=self.properties.get("default_cat", ""))
        self.notes.append(note)
        note.show()
        return note

    def showall(self, *args, **kwargs):
        for note in self.notes:
            note.show(*args, **kwargs)
        self.properties["all_visible"] = True

    def hideall(self, *args):
        self.save()
        for note in self.notes:
            note.hide(*args)
        self.properties["all_visible"] = False

    def get_category_property(self, cat, prop):
        """Get a property of a category or the default"""
        if ((not cat) or (not cat in self.categories)) and \
                self.properties.get("default_cat", None):
            cat = self.properties["default_cat"]
        cat_data = self.categories.get(cat, {})
        if prop in cat_data:
            return cat_data[prop]
        # Otherwise, use fallback categories
        if prop in FALLBACK_PROPERTIES:
            return FALLBACK_PROPERTIES[prop]
        else:
            raise ValueError("Unknown property")


class HTTPMonitorUpdater:
    def __init__(self, note, address, update_interval):
        self.note = note
        self.address = address
        self.update_interval = update_interval
        # self.update()
        self.interval = None

    def update(self):
        contents = urllib.request.urlopen(self.address).read()
        self.note.update(contents.decode("utf-8"))
        # contents = "fatman/anaconda2/envs/dev3/lib/python3.6/site-packages/torch/_C.cpython-36m"
        # self.note.update(contents)
        if self.note.gui != None:
            self.note.gui.update_body()
        # print('Updated from: ', self.address, '\n Contents:', contents.decode("utf-8"))
        print('(', time.time() ,') Updated from: ', self.address, '\n Contents:', contents)

    def start(self):
        print('Start')
        if self.interval != None:
            self.stop()
        self.interval = setInterval(self.update, 5)

    def stop(self):
        print('Stop')
        if self.interval != None:
            self.interval.cancel()
            self.interval = None

    def set_address(self, address):
        print('address', address)
        self.address = address

    def set_update_interval(self, update_interval):
        self.update_interval = update_interval


class setInterval:
    def __init__(self,action,interval) :
        self.interval=interval
        self.action=action
        self.stopEvent=threading.Event()
        thread=threading.Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self) :
        nextTime=time.time()+self.interval
        while not self.stopEvent.wait(nextTime-time.time()) :
            nextTime+=self.interval
            self.action()

    def cancel(self) :
        self.stopEvent.set()


class dGUI:
    """Dummy GUI"""
    def __init__(self, *args, **kwargs):
        pass
    def show(self):
        pass
    def hide(self):
        pass
    def update_note(self):
        pass
    def properties(self):
        return None
