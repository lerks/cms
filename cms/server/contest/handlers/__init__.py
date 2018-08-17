#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2015 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
# Copyright © 2015-2016 William Di Luigi <williamdiluigi@gmail.com>
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

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa


from .base import app, templated, contest_list_handler, fetch
from .contest import contest_bp, authentication_required, \
    actual_phase_required, get_task, get_submission, get_user_test, \
    notify_error, notify_warning, notify_success

from .main import main_handler, login_handler, start_handler, logout_handler, \
    notifications_handler, printing_handler_get, printing_handler_post, \
    documentation_handler
from .communication import communication_handler, question_handler
from .task import task_description_handler, task_statement_view_handler, \
    task_attachment_view_handler
from .tasksubmission import submit_handler, task_submissions_handler, \
    submission_status_handler, submission_details_handler, \
    submission_file_handler, use_token_handler
from .taskusertest import user_test_interface_handler, user_test_handler, \
    user_test_status_handler, user_test_details_handler, user_test_io_handler, \
    user_test_file_handler
