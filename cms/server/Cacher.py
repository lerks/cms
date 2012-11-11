#!/usr/bin/python
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2012 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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


import select

from sqlalchemy.engine.url import make_url

import psycopg2
import psycopg2.extensions

from cms.db.SQLAlchemyAll import Session, \
    Contest, Announcement, \
    Task, Statement, Attachment, SubmissionFormatElement, \
    User, Message, Question, \
    Submission, Token, File, \
    UserTest, UserTestFile, UserTestManager
from cms.db.SQLAlchemyUtils import classes as mapped_classes

from sqlalchemy.orm.util import identity_key
from sqlalchemy.orm import class_mapper

import tornado.ioloop

from cms import config as cms_config



database_url = make_url(cms_config.database)
assert database_url.get_dialect().driver == "psycopg2"


class Cacher(object):
    def __init__(self, contest_id, io_loop=None):
        self.pg_conn = psycopg2.connect(
            host=database_url.host,
            port=database_url.port,
            user=database_url.username,
            password=database_url.password,
            database=database_url.database,
            async=1,
            **database_url.query)
        self._wait()
        # XXX WTF??? (Explain)
        # self.pg_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

        # FIXME Do we handle double operations correctly?
        # (i.e. are we sure to catch all object modified WHILE we start?)

        self.pg_curs = self.pg_conn.cursor()
        # FIXME do we need a ._wait()?
        self.pg_curs.execute("LISTEN row_create;"
                             "LISTEN row_update;"
                             "LISTEN row_delete;")
        self._wait()

        self.io_loop = io_loop or tornado.ioloop.IOLoop.instance()
        self.io_loop.add_handler(self.pg_conn.fileno(), self._callback, self.io_loop.READ)

        self.session = Session(autocommit=True)
        self.objects = dict()

        # Not sure whether we should use local_table or mapped_table
        self.tables_to_classes = dict(
            (class_mapper(cls).local_table.name, cls)
            for cls in mapped_classes.itervalues())

        self._first_load(contest_id)
        self.submissions = dict()  # Indexed by username and taskname
        self.user_tests = dict()  # Indexed by username and taskname


    def __del__(self):
        self.io_loop.remove_handler(self.pg_conn.fileno())

        # We could close the PostgreSQL connection by explictly calling
        # its .close() method, but we rely on it being deleted by the
        # garbage collector and closed by its __del__ method.

    def _wait(self):
        # FIXME I guess we can simplify this code a bit...
        while True:
            state = self.pg_conn.poll()
            if state == psycopg2.extensions.POLL_OK:
                break
            elif state == psycopg2.extensions.POLL_WRITE:
                select.select([], [self.pg_conn.fileno()], [])
            elif state == psycopg2.extensions.POLL_READ:
                select.select([self.pg_conn.fileno()], [], [])
            else:
                raise psycopg2.OperationalError("poll() returned %s" % state)

    def _callback(self, fd, events):
        # TODO Hmm... could this raise an exception in case some error happened?
        # (like... the server died, our connection broke, etc.)
        self.pg_conn.poll()

        print type(self.pg_conn.notifies)  # FIXME remove
        # It seems to be a list: we could just iterate
        while self.pg_conn.notifies:
            notify = self.pg_conn.notifies.pop()

            # FIXME Can we use notify.pid somehow?
            event = notify.channel
            table, _tmp, id_ = notify.payload.rpartition(' ')
            cls = self.tables_to_classes[table]
            id_ = int(id_)

            self.trigger(event, cls, id_)


    CREATE = "create" # FIXME Mmh... row_?
    UPDATE = "update"
    DELETE = "delete"

    def trigger(self, event, cls, id_):
        key = identity_key(cls, id_)

        old_obj = self.objects.get(key, None)

        if event == "row_create" or event == "row_update": # XXX
            new_obj = cls.get_from_id(id_, self.session)
            self.session.expunge(new_obj)

            # TODO When (if?) we introduce some kind of version number
            # in the DB we could use it to see if we can break here.

            if self._want_to_keep(new_obj):
                if old_obj is not None:
                    # UPDATE
                    self.objects[key] = new_obj
                    self._do_update(old_obj, new_obj)
                    # TODO Call event listeners
                else:
                    # CREATE
                    self.objects[key] = new_obj
                    self._do_create(new_obj)
                    # TODO Call event listeners
            else:
                event = "row_delete" # XXX

        elif event == "row_delete": # XXX
            if old_obj is not None:
                # DELETE
                del self.objects[key]
                self._do_delete(old_obj)
                # TODO Call event listeners
            else:
                # Nothing to be done
                pass

        else:
            raise RuntimeError("Unknown event '%s'" % event)


    def _want_to_keep(self, obj):
        # This method is horrible: any suggestion is welcome!
        if isinstance(obj, Contest):
            return identity_key(Contest, obj.id) in self.objects
        if isinstance(obj, Announcement):
            return identity_key(Contest, obj.contest_id) in self.objects

        if isinstance(obj, Task):
            return identity_key(Contest, obj.contest_id) in self.objects
        if isinstance(obj, Statement):
            return identity_key(Task, obj.task_id) in self.objects
        if isinstance(obj, Attachment):
            return identity_key(Task, obj.task_id) in self.objects
        if isinstance(obj, SubmissionFormatElement):
            return identity_key(Task, obj.task_id) in self.objects

        if isinstance(obj, User):
            return identity_key(User, obj.id) in self.objects
        if isinstance(obj, Message):
            return identity_key(User, obj.user_id) in self.objects
        if isinstance(obj, Question):
            return identity_key(User, obj.user_id) in self.objects

        if isinstance(obj, Submission):
            # Only if we are already tracking its user
            # FIXME Explain better
            user = self.objects[identity_key(User, obj.user_id)]
            return user in self.submissions
        if isinstance(obj, Token):
            return identity_key(Submission, obj.submission_id) in self.objects
        if isinstance(obj, File):
            return identity_key(Submission, obj.submission_id) in self.objects

        if isinstance(obj, UserTest):
            # Only if we are already tracking its user
            # FIXME Explain better
            user = self.objects[identity_key(User, obj.user_id)]
            return user in self.user_tests
        if isinstance(obj, UserTestFile):
            return identity_key(UserTest, obj.user_test_id) in self.objects
        if isinstance(obj, UserTestManager):
            return identity_key(UserTest, obj.user_test_id) in self.objects

        # We don't know the object's type: we don't want to keep it!
        return False



    def _do_create(self, obj):
        # TODO We could try setting just the .parent relationship and
        # hope the reverse (i.e. the backref) is set up automatically.

        if isinstance(obj, Contest):
            self.contest = obj
        if isinstance(obj, Announcement):
            contest = self.objects[identity_key(Contest, obj.contest_id)]
            contest.announcements.append(obj)
            contest.announcements.sort(key=lambda a: (a.timestamp))

        if isinstance(obj, Task):
            contest = self.objects[identity_key(Contest, obj.contest_id)]
            contest.tasks.append(obj)
            contest.tasks.sort(key=lambda a: (a.num))
            # Create child dict in self.submissions and self.user_tests
            for v in self.submissions.itervalues():
                v[obj] = dict()
            for v in self.user_tests.itervalues():
                v[obj] = dict()
        if isinstance(obj, Statement):
            task = self.objects[identity_key(Task, obj.task_id)]
            task.statements[obj.language] = obj
        if isinstance(obj, Attachment):
            task = self.objects[identity_key(Task, obj.task_id)]
            task.attachments[obj.filename] = obj
        if isinstance(obj, SubmissionFormatElement):
            task = self.objects[identity_key(Task, obj.task_id)]
            task.submission_format.append(obj)  # FIXME not so sure...

        if isinstance(obj, User):
            contest = self.objects[identity_key(Contest, obj.contest_id)]
            contest.tasks.append(obj)
            # We DON'T create dict in self.submissions and self.user_tests!
        if isinstance(obj, Message):
            user = self.objects[identity_key(User, obj.user_id)]
            user.messages.append(obj)
            user.messages.sort(key=lambda a: (a.timestamp))
        if isinstance(obj, Question):
            user = self.objects[identity_key(User, obj.user_id)]
            user.questions.append(obj)
            user.questions.sort(key=lambda a: (a.question_timestamp, a.reply_timestamp))

        if isinstance(obj, Submission):
            task = self.objects[identity_key(Task, obj.task_id)]
            user = self.objects[identity_key(User, obj.user_id)]
            self.submissions[user][task].append(obj)
            self.submissions[user][task].sort(key=lambda a: (a.timestamp))
        if isinstance(obj, Token):
            submission = self.objects[identity_key(Submission, obj.submission_id)]
            submission.token = obj
        if isinstance(obj, File):
            submission = self.objects[identity_key(Submission, obj.submission_id)]
            submission.files[obj.filename] = obj

        if isinstance(obj, UserTest):
            task = self.objects[identity_key(Task, obj.task_id)]
            user = self.objects[identity_key(User, obj.user_id)]
            self.user_tests[user][task].append(obj)
            self.user_tests[user][task].sort(key=lambda a: (a.timestamp))
        if isinstance(obj, UserTestFile):
            user_test = self.objects[identity_key(UserTest, obj.user_test_id)]
            user_test.files[obj.filename] = obj
        if isinstance(obj, UserTestManager):
            user_test = self.objects[identity_key(UserTest, obj.user_test_id)]
            user_test.files[obj.filename] = obj

    def _do_update(self, old_obj, new_obj):
        self._do_delete(old_obj)
        self._do_create(new_obj)

    def _do_delete(self, obj):
        # TODO We could try removing just the .parent relationship and
        # hope the reverse (i.e. the backref) is set up automatically.

        if isinstance(obj, Contest):
            # FIXME WTF? I think we should just fail lodly!
            pass
        if isinstance(obj, Announcement):
            contest = self.objects[identity_key(Contest, obj.contest_id)]
            contest.announcements.remove(obj)

        if isinstance(obj, Task):
            contest = self.objects[identity_key(Contest, obj.contest_id)]
            contest.tasks.remove(obj)
            # Delete child dict in self.submissions and self.user_tests
            for v in self.submissions.itervalues():
                del v[obj]  # FIXME Do we want to assert its emptiness? (Hint: see deletion order for CASCADES)
            for v in self.user_tests.itervalues():
                del v[obj]  # FIXME Do we want to assert its emptiness? (Hint: see deletion order for CASCADES)
        if isinstance(obj, Statement):
            task = self.objects[identity_key(Task, obj.task_id)]
            del task.statements[obj.language]
        if isinstance(obj, Attachment):
            task = self.objects[identity_key(Task, obj.task_id)]
            del task.attachments[obj.filename]
        if isinstance(obj, SubmissionFormatElement):
            task = self.objects[identity_key(Task, obj.task_id)]
            task.submission_format.remove(obj)  # FIXME not so sure...

        if isinstance(obj, User):
            contest = self.objects[identity_key(Contest, obj.contest_id)]
            contest.users.remove(obj)
            # FIXME Should we delete dict in self.submissions and self.user_tests?
        if isinstance(obj, Message):
            user = self.objects[identity_key(User, obj.user_id)]
            user.messages.remove(obj)
        if isinstance(obj, Question):
            user = self.objects[identity_key(User, obj.user_id)]
            user.questions.remove(obj)

        if isinstance(obj, Submission):
            # This has to be handled differently
            task = self.objects[identity_key(Task, obj.task_id)]
            user = self.objects[identity_key(User, obj.user_id)]
            self.submissions[user][task].remove(obj)
        if isinstance(obj, Token):
            submission = self.objects[identity_key(Submission, obj.submission_id)]
            submission.token = None
        if isinstance(obj, File):
            submission = self.objects[identity_key(Submission, obj.submission_id)]
            del submission.files[obj.filename]

        if isinstance(obj, UserTest):
            # This has to be handled differently
            task = self.objects[identity_key(Task, obj.task_id)]
            user = self.objects[identity_key(User, obj.user_id)]
            self.user_tests[user][task].remove(obj)
        if isinstance(obj, UserTestFile):
            user_test = self.objects[identity_key(UserTest, obj.user_test_id)]
            del user_test.files[obj.filename]
        if isinstance(obj, UserTestManager):
            user_test = self.objects[identity_key(UserTest, obj.user_test_id)]
            del user_test.files[obj.filename]



    def _first_load(self, contest_id):
        contest = Contest.get_from_id(contest_id, self.session)
        self.objects[contest._identity_key] = contest

        for announcement in contest.announcements:
            self.objects[announcement._identity_key] = announcement
            self.session.expunge(announcement)

        for task in contest.tasks:
            self.objects[task._identity_key] = task

            for statement in task.statements:
                self.objects[statement._identity_key] = statement
                self.session.expunge(statement)
            for attachment in task.attachments:
                self.objects[attachment._identity_key] = attachment
                self.session.expunge(attachment)
            for submission_format_element in task.submission_format:
                self.objects[submission_format_element._identity_key] = submission_format_element
                self.session.expunge(submission_format_element)

            self.session.expunge(task)

        for user in contest.users:
            self.objects[user._identity_key] = user

            for message in user.messages:
                self.objects[message._identity_key] = message
                self.session.expunge(message)
            for question in user.questions:
                self.objects[question._identity_key] = question
                self.session.expunge(question)

            self.session.expunge(user)

        self.session.expunge(contest)

        self.contest = contest

    def get_submissions(self, user, task):
        # FIXME Assert user and task existence?
        if user not in self.submissions:
            submissions = self.session.query(Submission)\
                .filter(Submission.user == user)\
                .order_by(Submission.timestamp)\
                .scalar()

            self.submissions[user] = dict()
            for s in submissions:
                self.objects[s._identity_key] = s

                if s.token is not None:
                    self.objects[s.token._identity_key] = s.token
                    self.session.expunge(s.token)

                for file_ in s.files:
                    self.objects[file_._identity_key] = file
                    self.session.expunge(file_)

                self.session.expunge(s)

                task = self.objects[identity_key(Task, s.task_id)]
                self.submissions[user].setdefault(task, []).append(s)

        return self.submissions[user][task]


    def get_user_tests(self, user, task):
        # FIXME Assert user and task existence?
        if user not in self.user_tests:
            user_tests = self.session.query(UserTest)\
                .filter(UserTest.user == user)\
                .order_by(UserTest.timestamp)\
                .scalar()

            self.user_tests[user] = dict()
            for u in user_tests:
                self.objects[u._identity_key] = u

                for file_ in u.files:
                    self.objects[file_._identity_key] = file
                    self.session.expunge(file_)

                for manager in s.managers:
                    self.objects[manager._identity_key] = manager
                    self.session.expunge(manager)

                self.session.expunge(u)

                task = self.objects[identity_key(Task, u.task_id)]
                self.user_tests[user].setdefault(task, []).append(u)

        return self.user_tests[user][task]
