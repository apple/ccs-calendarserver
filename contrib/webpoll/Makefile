##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
	curl http://code.jquery.com/jquery-2.0.3.js -o webapp/js/jquery-2.0.3.js
	curl http://code.jquery.com/ui/1.10.3/jquery-ui.js -o webapp/js/jquery-ui-1.10.3.js
	curl https://raw.github.com/douglascrockford/JSON-js/master/json2.js -o webapp/js/json2.js
	curl http://trentrichardson.com/examples/timepicker/jquery-ui-timepicker-addon.js -o webapp/js/datetimepicker.js
	
	curl http://trentrichardson.com/examples/timepicker/jquery-ui-timepicker-addon.css -o webapp/css/datetimepicker.css
	curl http://jqueryui.com/resources/download/jquery-ui-themes-1.10.3.zip -o /tmp/jquery-ui-themes-1.10.3.zip
	unzip /tmp/jquery-ui-themes-1.10.3.zip jquery-ui-themes-1.10.3/themes/cupertino/* -d /tmp
	mv /tmp/jquery-ui-themes-1.10.3/themes/cupertino webapp/css
	rm -rf /tmp/jquery-ui-themes-1.10.3

clean:
	rm -f webapp/js/jquery-2.0.3.js
	rm -f webapp/js/jquery-ui-1.10.3.js
	rm -f webapp/js/json2.js
	rm -f webapp/js/datetimepicker.js
	
	rm -f webapp/css/datetimepicker.css
	rm -rf webapp/css/cupertino
