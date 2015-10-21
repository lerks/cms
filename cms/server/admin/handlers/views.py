#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2015 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2015 Luca Wehrstedt <luca.wehrstedt@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""UI fragments for AdminWebServer

"""


import tornado.web


class ReevaluationButtons(tornado.web.UIModule):
    def render(self, url_root, url, **invalidate_arguments):
        """Render reevaluation buttons for the given filters.

        url_root (unicode): path to the root of the server.
        url (unicode): the url to redirect the user to after they
            performed the reevaluation.
        invalidate_arguments (dict): a set of constraints, of the form
            "<entity>_id: <int>", defining which submissions have to be
            reevaluated; accepts all combinations supported by the
            invalidate_submission method of ES and SS.

        """
        return self.render_string(
            "views/reevaluation_buttons.html",
            url_root=url_root,
            url=url,
            invalidate_arguments=invalidate_arguments)
