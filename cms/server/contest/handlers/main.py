#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2018 Stefano Maggiolo <s.maggiolo@gmail.com>
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

"""Non-categorized handlers for CWS.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import ipaddress
import logging
from datetime import timedelta

from flask import g, request, redirect, abort, url_for, current_app, \
    after_this_request, jsonify

from cms import config
from cms.db import PrintJob, ScopedSession
from cms.grading.steps import COMPILATION_MESSAGES, EVALUATION_MESSAGES
from cms.server.contest.authentication import validate_login
from cms.server.contest.communication import get_communications
from cms.server.contest.printing import accept_print_job, PrintingDisabled, \
    UnacceptablePrintJob
from cmscommon.datetime import make_datetime, make_timestamp

from ..phase_management import actual_phase_required

from . import contest_bp
from .base import templated, authentication_required, notify_success, notify_error


logger = logging.getLogger(__name__)


# Dummy function to mark translatable strings.
def N_(msgid):
    return msgid


@contest_bp.route("/", methods=["GET"])
@templated("overview.html")
def main_handler(self):
    """Home page handler.

    """
    pass


@contest_bp.route("/login", methods=["POST"])
def login_handler():
        """Login handler.

        """
        error_args = {"login_error": "true"}
        next_page = request.args.get("next", None)
        if next_page is not None:
            error_args["next"] = next_page
        else:
            next_page = url_for("contest.main_handler")
        error_page = url_for("contest.main_handler", **error_args)

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        try:
            # In py2 Tornado gives us the IP address as a native binary
            # string, whereas ipaddress wants text (unicode) strings.
            ip_address = ipaddress.ip_address(str(request.remote_addr))
        except ValueError:
            logger.warning("Invalid IP address provided by Flask: %s",
                           request.remote_addr)
            return None

        participation, cookie = validate_login(
            ScopedSession(), g.contest, g.timestamp, username, password,
            ip_address)

        cookie_name = g.contest.name + "_login"
        expires = g.timestamp - timedelta(days=365)
        @after_this_request
        def update_cookie(response):
            if cookie is None:
                response.set_cookie(cookie_name, "", expires=expires)
            else:
                # FIXME Secure?
                response.set_cookie(cookie_name, cookie, expires_days=None)


        if participation is None:
            return redirect(error_page)
        else:
            return redirect(next_page)


@contest_bp.route("/start", methods=["POST"])
@authentication_required()
@actual_phase_required(-1)
def start_handler():
        """Start handler.

        Used by a user who wants to start their per_user_time.

        """
        participation = g.participation

        logger.info("Starting now for user %s", participation.user.username)
        participation.starting_time = g.timestamp
        ScopedSession().commit()

        return redirect(url_for("contest.main_handler"))


@contest_bp.route("/logout", method=["POST"])
@authentication_required()
def logout_handler():
        """Logout handler.

        """
        cookie_name = g.contest.name + "_login"
        expires = g.timestamp - timedelta(days=365)
        @after_this_request
        def update_cookie(response):
            response.set_cookie(cookie_name, "", expires=expires)
        return redirect(url_for("contest.main_handler"))


@contest_bp.route("/notifications", methods=["GET"])
@authentication_required(refresh_cookie=False)
def notifications_handler():
        """Displays notifications.

        """
        participation = g.participation

        last_notification = request.args.get("last_notification", None)
        if last_notification is not None:
            last_notification = make_datetime(float(last_notification))

        res = get_communications(ScopedSession(), participation,
                                 g.timestamp, after=last_notification)

        # Simple notifications
        notifications = current_app.service.notifications
        username = participation.user.username
        if username in notifications:
            for notification in notifications[username]:
                res.append({"type": "notification",
                            "timestamp": make_timestamp(notification[0]),
                            "subject": notification[1],
                            "text": notification[2],
                            "level": notification[3]})
            del notifications[username]

        return jsonify(res)


@contest_bp.route("/printing", methods=["GET"])
@authentication_required()
@actual_phase_required(0)
@templated("printing.html")
def printing_handler_get():
        """Serve the interface to print and handle submitted print jobs.

        """
        participation = g.participation

        if config.printer is None:
            abort(404)

        printjobs = ScopedSession().query(PrintJob)\
            .filter(PrintJob.participation == participation)\
            .all()

        remaining_jobs = max(0, config.max_jobs_per_user - len(printjobs))

        return {"printjobs": printjobs,
                "remaining_jobs": remaining_jobs,
                "max_pages": config.max_pages_per_job,
                "pdf_printing_allowed": config.pdf_printing_allowed}


@contest_bp.route("/printing", methods=["POST"])
@authentication_required()
@actual_phase_required(0)
def printing_handler_post():
        try:
            printjob = accept_print_job(
                ScopedSession(), current_app.service.file_cacher, g.participation,
                g.timestamp, request.files.to_dict(flat=False))
            ScopedSession().commit()
        except PrintingDisabled:
            abort(404)
        except UnacceptablePrintJob as e:
            notify_error(e.subject, e.text)
        else:
            current_app.service.printing_service.new_printjob(printjob_id=printjob.id)
            notify_success(N_("Print job received"),
                           N_("Your print job has been received."))

        return redirect(url_for("contest.printing_handler_get"))


@contest_bp.route("/documentation", methods=["GET"])
@authentication_required()
@templated("documentation.html")
def documentation_handler():
        """Displays the instruction (compilation lines, documentation,
        ...) of the contest.

        """
        return {"COMPILATION_MESSAGES": COMPILATION_MESSAGES,
                "EVALUATION_MESSAGES": EVALUATION_MESSAGES}
