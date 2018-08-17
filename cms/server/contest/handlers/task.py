#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2017 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2018 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
# Copyright © 2015-2016 William Di Luigi <williamdiluigi@gmail.com>
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

"""Task-related handlers for CWS.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import logging

from flask import g, abort

from cmscommon.mimetypes import get_type_for_file_name

from . import contest_bp, authentication_required, actual_phase_required, \
    templated, fetch, get_task


logger = logging.getLogger(__name__)


@contest_bp.route("/tasks/<task_name>/description", methods=["GET"])
@authentication_required()
@actual_phase_required(0, 3)
@templated("task_description.html")
def task_description_handler(task_name):
        """Shows the data of a task in the contest.

        """
        task = get_task(task_name)
        if task is None:
            abort(404)

        return {"task": task}


@contest_bp.route("/tasks/<task_name>/statements/<lang_code>", methods=["GET"])
@authentication_required()
@actual_phase_required(0, 3)
def task_statement_view_handler(task_name, lang_code):
        """Shows the statement file of a task in the contest.

        """
        task = get_task(task_name)
        if task is None:
            abort(404)

        if lang_code not in task.statements:
            abort(404)

        statement = task.statements[lang_code].digest
        g.session.close()

        if len(lang_code) > 0:
            filename = "%s (%s).pdf" % (task.name, lang_code)
        else:
            filename = "%s.pdf" % task.name

        fetch(statement, "application/pdf", filename)


@contest_bp.route("/tasks/<task_name>/attachments/<filename>", methods=["GET"])
@authentication_required()
@actual_phase_required(0, 3)
def task_attachment_view_handler(task_name, filename):
        """Shows an attachment file of a task in the contest.

        """
        task = get_task(task_name)
        if task is None:
            abort(404)

        if filename not in task.attachments:
            abort(404)

        attachment = task.attachments[filename].digest
        g.session.close()

        mimetype = get_type_for_file_name(filename)
        if mimetype is None:
            mimetype = 'application/octet-stream'

        fetch(attachment, mimetype, filename)
