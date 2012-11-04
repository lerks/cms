#!/usr/bin/python
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
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

"""This is the main inteface to the db objects. In particular, every
db objects must be imported from this module.

"""

import sys

from cms.db.SQLAlchemyUtils import db, Base, metadata, Session, \
     ScopedSession, SessionGen

from cms.db.Contest import \
    Contest, \
    Announcement
from cms.db.User import \
    User, \
    Message, \
    Question
from cms.db.Task import \
    Task, \
    Manager, \
    Testcase, \
    Attachment, \
    SubmissionFormatElement, \
    Statement
from cms.db.Submission import \
    Submission, \
    Token, \
    Evaluation, \
    File, \
    Executable
from cms.db.UserTest import \
    UserTest, \
    UserTestFile, \
    UserTestExecutable, \
    UserTestManager
from cms.db.FSObject import \
    FSObject


metadata.create_all()


if __name__ == "__main__":
    if "redrop" in sys.argv[1:]:
        metadata.drop_all()
