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
import json
import logging

import tornado.web
from flask import g

from cms import config
from cms.db import PrintJob
from cms.grading.steps import COMPILATION_MESSAGES, EVALUATION_MESSAGES
from cms.server import multi_contest
from cms.server.contest.authentication import validate_login
from cms.server.contest.communication import get_communications
from cms.server.contest.printing import accept_print_job, PrintingDisabled, \
    UnacceptablePrintJob
from cms.db import Participation, PrintJob, User, ScopedSession
from cms.grading import COMPILATION_MESSAGES, EVALUATION_MESSAGES
from cms.server import actual_phase_required, filter_ascii
from cms.server.contest.authentication import check_ip
from cms.server.contest.handlers import contest_bp
from cms.server.contest.handlers.base import templated, authentication_required
from cmscommon.datetime import make_datetime, make_timestamp

from ..phase_management import actual_phase_required

from .contest import ContestHandler
from .contest import NOTIFICATION_ERROR, NOTIFICATION_SUCCESS


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
        next_page = self.get_argument("next", None)
        if next_page is not None:
            error_args["next"] = next_page
            if next_page != "/":
                next_page = self.url(*next_page.strip("/").split("/"))
            else:
                next_page = self.url()
        else:
            next_page = self.contest_url()
        error_page = self.contest_url(**error_args)

        username = self.get_argument("username", "")
        password = self.get_argument("password", "")

        try:
            # In py2 Tornado gives us the IP address as a native binary
            # string, whereas ipaddress wants text (unicode) strings.
            ip_address = ipaddress.ip_address(str(self.request.remote_ip))
        except ValueError:
            logger.warning("Invalid IP address provided by Tornado: %s",
                           self.request.remote_ip)
            return None

        participation, cookie = validate_login(
            self.sql_session, self.contest, self.timestamp, username, password,
            ip_address)

        cookie_name = self.contest.name + "_login"
        if cookie is None:
            self.clear_cookie(cookie_name)
        else:
            self.set_secure_cookie(cookie_name, cookie, expires_days=None)

        if participation is None:
            self.redirect(error_page)
        else:
            self.redirect(next_page)


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

        self.redirect(self.contest_url())


@contest_bp.route("/logout", method=["POST"])
@authentication_required()
def logout_handler():
        """Logout handler.

        """
        self.clear_cookie(g.contest.name + "_login")
        self.redirect(self.contest_url())


@contest_bp.route("/notifications", methods=["GET"])
@authentication_required(refresh_cookie=False)
def notifications_handler():
        """Displays notifications.

        """
        participation = g.participation

        last_notification = self.get_argument("last_notification", None)
        if last_notification is not None:
            last_notification = make_datetime(float(last_notification))

        res = get_communications(self.sql_session, participation,
                                 self.timestamp, after=last_notification)

        # Simple notifications
        notifications = self.service.notifications
        username = participation.user.username
        if username in notifications:
            for notification in notifications[username]:
                res.append({"type": "notification",
                            "timestamp": make_timestamp(notification[0]),
                            "subject": notification[1],
                            "text": notification[2],
                            "level": notification[3]})
            del notifications[username]

        self.write(json.dumps(res))


@contest_bp.route("/printing", methods=["GET"])
@authentication_required()
@actual_phase_required(0)
@templated("printing.html")
def printing_handler_get():
        """Serve the interface to print and handle submitted print jobs.

        """
        participation = g.participation

        if not self.r_params["printing_enabled"]:
            raise tornado.web.HTTPError(404)

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
                self.sql_session, self.service.file_cacher, self.current_user,
                self.timestamp, self.request.files)
            self.sql_session.commit()
        except PrintingDisabled:
            raise tornado.web.HTTPError(404)
        except UnacceptablePrintJob as e:
            self.notify_error(e.subject, e.text)
        else:
            self.service.printing_service.new_printjob(printjob_id=printjob.id)
            self.notify_success(N_("Print job received"),
                                N_("Your print job has been received."))

        self.redirect(self.contest_url("printing"))


@contest_bp.route("/documentation", methods=["GET"])
@authentication_required()
@templated("documentation.html")
def documentation_handler():
        """Displays the instruction (compilation lines, documentation,
        ...) of the contest.

        """
        return {"COMPILATION_MESSAGES": COMPILATION_MESSAGES,
                "EVALUATION_MESSAGES": EVALUATION_MESSAGES}
