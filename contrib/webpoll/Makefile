##
# Copyright (c) 2013-2015 Apple Inc. All rights reserved.
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

webpoll:
	mkdir -p webapp/js/3rdparty
	curl http://code.jquery.com/jquery-2.1.3.js -o webapp/js/3rdparty/jquery-2.1.3.js
	curl http://code.jquery.com/ui/1.11.2/jquery-ui.js -o webapp/js/3rdparty/jquery-ui-1.11.2.js
	curl -L https://github.com/douglascrockford/JSON-js/raw/master/json2.js -o webapp/js/3rdparty/json2.js
	curl http://trentrichardson.com/examples/timepicker/jquery-ui-timepicker-addon.js -o webapp/js/3rdparty/datetimepicker.js
	
	mkdir -p webapp/css/3rdparty
	curl http://trentrichardson.com/examples/timepicker/jquery-ui-timepicker-addon.css -o webapp/css/3rdparty/datetimepicker.css
	curl http://jqueryui.com/resources/download/jquery-ui-themes-1.11.2.zip -o /tmp/jquery-ui-themes-1.11.2.zip
	unzip /tmp/jquery-ui-themes-1.11.2.zip jquery-ui-themes-1.11.2/themes/cupertino/* -d /tmp
	mv /tmp/jquery-ui-themes-1.11.2/themes/cupertino webapp/css/3rdparty
	rm -rf /tmp/jquery-ui-themes-1.11.2

clean:
	rm -rf webapp/js/3rdparty
	rm -rf webapp/css/3rdparty
