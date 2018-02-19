#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2016 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2017 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
# Copyright © 2015-2016 William Di Luigi <williamdiluigi@gmail.com>
# Copyright © 2016 Myungwoo Chun <mc.tamaki@gmail.com>
# Copyright © 2016 Amir Keivan Mohtashami <akmohtashami97@gmail.com>
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

"""Contest handler classes for CWS.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa
from six import iterkeys, iteritems

import logging

import tornado.web

from cms import config
from cms.db import Contest, Submission, Task, UserTest
from cms.server import FileHandlerMixin
from cms.locale import filter_language_codes
from cms.server.contest.authentication import authenticate_request
from cmscommon.datetime import get_timezone

from ..phase_management import compute_actual_phase

from .base import BaseHandler


logger = logging.getLogger(__name__)


NOTIFICATION_ERROR = "error"
NOTIFICATION_WARNING = "warning"
NOTIFICATION_SUCCESS = "success"


class ContestHandler(BaseHandler):
    """A handler that has a contest attached.

    Most of the RequestHandler classes in this application will be a
    child of this class.

    """
    def __init__(self, *args, **kwargs):
        super(ContestHandler, self).__init__(*args, **kwargs)
        self.contest_url = None

    def prepare(self):
        if self.contest.allowed_localizations:
            lang_codes = filter_language_codes(
                list(iterkeys(self.available_translations)),
                self.contest.allowed_localizations)
            self.available_translations = dict(
                (k, v) for k, v in iteritems(self.available_translations)
                if k in lang_codes)

        super(ContestHandler, self).prepare()

        # Run render_params() now, not at the beginning of the request,
        # because we need contest_name
        self.r_params = self.render_params()



class FileHandler(ContestHandler, FileHandlerMixin):
    pass
