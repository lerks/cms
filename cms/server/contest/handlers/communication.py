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

"""Communication-related handlers for CWS.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import logging

from flask import redirect, abort, request, url_for, g

from cms.server.contest.communication import accept_question, \
    UnacceptableQuestion, QuestionsNotAllowed

from . import contest_bp, authentication_required, templated, notify_error, \
    notify_success


logger = logging.getLogger(__name__)


# Dummy function to mark translatable strings.
def N_(msgid):
    return msgid


@contest_bp.route("/communication", methods=["GET"])
@templated("communication.html")
def communication_handler():
        """Displays the private conversations between the logged in user
        and the contest managers..

        """
        pass


@contest_bp.route("/question", methods=["POST"])
@authentication_required()
def question_handler():
        """Called when the user submits a question.

        """
        try:
            accept_question(g.session, g.participation, g.timestamp,
                            request.form.get("question_subject", ""),
                            request.form.get("question_text", ""))
            g.session.commit()
        except QuestionsNotAllowed:
            abort(404)
        except UnacceptableQuestion as e:
            notify_error(e.subject, e.text)
        else:
            notify_success(N_("Question received"),
                           N_("Your question has been received, you "
                              "will be notified when it is answered."))

        return redirect(url_for("contest.communication_handler"))
