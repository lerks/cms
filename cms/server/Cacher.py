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

        # FIXME Do we handle double operations correctly?
        # (i.e. are we sure to catch all object modified WHILE we start?)

        cursor = self.pg_conn.cursor()
        cursor.execute("LISTEN row_create;"
                       "LISTEN row_update;"
                       "LISTEN row_delete;")
        self._wait()

        self.io_loop = io_loop or tornado.ioloop.IOLoop.instance()
        self.io_loop.add_handler(self.pg_conn.fileno(), self._callback, self.io_loop.READ)

        self.session = Session(autocommit=True)

        # Not sure whether we should use local_table or mapped_table
        self.tables_to_classes = dict(
            (class_mapper(cls).mapped_table.name, cls)
            for cls in mapped_classes.itervalues())

        self.contest = Contest.get_from_id(contest_id, self.session)
        self.submissions = dict()  # Indexed by username and taskname
        self.user_tests = dict()  # Indexed by username and taskname


    def __del__(self):
        self.io_loop.remove_handler(self.pg_conn.fileno())

        # We could close the PostgreSQL connection by explictly calling
        # its .close() method, but we rely on it being deleted by the
        # garbage collector and closed by its __del__ method.

    def _wait(self):
        while True:
            state = self.pg_conn.poll()
            if state == psycopg2.extensions.POLL_OK:
                break
            elif state == psycopg2.extensions.POLL_WRITE:
                select.select([], [self.pg_conn], [])
            elif state == psycopg2.extensions.POLL_READ:
                select.select([self.pg_conn], [], [])
            else:
                raise psycopg2.OperationalError("poll() returned %s" % state)

    def _callback(self, fd, events):
        # TODO Hmm... could this raise an exception in case some error happened?
        # (like... the server died, our connection broke, etc.)
        self.pg_conn.poll()

        # It seems to be a list: we could just iterate
        for notify in self.pg_conn.notifies:
#            notify = self.pg_conn.notifies.pop()

            print
            print "NOTIFY"
            print notify.channel
            print notify.payload
            print

            # FIXME Can we use notify.pid somehow?
            event = notify.channel[4:]  # XXX XXX XXX
            table, _tmp, id_ = notify.payload.rpartition(' ')
            cls = self.tables_to_classes[table]
            id_ = int(id_)

            self.trigger(event, cls, id_)

        # TODO clear list


    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

    def get_object(self, cls, id_):
        return self.session.identity_map.get(identity_key(cls, id_), None)

    def trigger(self, event, cls, id_):
        print "\nGetting old object\n"
        old_obj = self.get_object(cls, id_)
        if old_obj is not None:
            print "\nNot None: deleting\n"
            self._do_delete(old_obj)
            print "\nRefreshing\n"
            self.session.refresh(old_obj)
            print "\nDone\n"

        if event == self.CREATE or event == self.UPDATE:
            print "\nGetting new object\n"
            new_obj = cls.get_from_id(id_, self.session)

            # TODO When (if?) we introduce some kind of version number
            # in the DB we could use it to see if we can break here.

            if new_obj is not None and self._want_to_keep(new_obj):
                print "\nWant to keep! Creating\n"
                self._do_create(new_obj)
                if old_obj is not None:
                    # UPDATE
                    # TODO Call event listeners
                    pass
                else:
                    # CREATE
                    # TODO Call event listeners
                    pass
            else:
                event = self.DELETE

        elif event == self.DELETE:
            print "\nDeleting (noop)\n"
            if old_obj is not None:
                # DELETE
                # TODO Call event listeners
                pass
            else:
                # Nothing to be done
                pass

        else:
            raise RuntimeError("Unknown event '%s'" % event)

        print "\nDONE\n"

        print "\nLoading contest"
        print self.contest

        print "\nLoading tasks"
        print self.contest.tasks

        print "\nLoading our task"
        print self.contest.tasks[0]

        print "\nAsserting identity"
        print self.contest.tasks[0] is new_obj

        print "\nGoing up"
        print self.contest.tasks[0].contest

        print "\nAsserting identity"
        print self.contest.tasks[0].contest is self.contest

        contest = self.get_contest()
        user = contest.get_user("luca")
        contest.tasks
        contest.tasks[0].token_gen_time
        contest.token_gen_time
        task = contest.get_task('test')
        self.get_submissions(user, task)
        task.testcases
        task.submission_format
        task.statements

        print "\nYep/Nope?\n"


    def _want_to_keep(self, obj):
        # This method is horrible: any suggestion is welcome!
        if isinstance(obj, Contest):
            return identity_key(Contest, obj.id) in self.session.identity_map
        if isinstance(obj, Announcement):
            return identity_key(Contest, obj.contest_id) in self.session.identity_map

        if isinstance(obj, Task):
            return identity_key(Contest, obj.contest_id) in self.session.identity_map
        if isinstance(obj, Statement):
            return identity_key(Task, obj.task_id) in self.session.identity_map
        if isinstance(obj, Attachment):
            return identity_key(Task, obj.task_id) in self.session.identity_map
        if isinstance(obj, SubmissionFormatElement):
            return identity_key(Task, obj.task_id) in self.session.identity_map

        if isinstance(obj, User):
            return identity_key(User, obj.id) in self.session.identity_map
        if isinstance(obj, Message):
            return identity_key(User, obj.user_id) in self.session.identity_map
        if isinstance(obj, Question):
            return identity_key(User, obj.user_id) in self.session.identity_map

        if isinstance(obj, Submission):
            # Only if we are already tracking its user
            # FIXME Explain better
            user = self.get_object(User, obj.user_id)
            return user in self.submissions
        if isinstance(obj, Token):
            return identity_key(Submission, obj.submission_id) in self.session.identity_map
        if isinstance(obj, File):
            return identity_key(Submission, obj.submission_id) in self.session.identity_map

        if isinstance(obj, UserTest):
            # Only if we are already tracking its user
            # FIXME Explain better
            user = self.get_object(User, obj.user_id)
            return user in self.user_tests
        if isinstance(obj, UserTestFile):
            return identity_key(UserTest, obj.user_test_id) in self.session.identity_map
        if isinstance(obj, UserTestManager):
            return identity_key(UserTest, obj.user_test_id) in self.session.identity_map

        # We don't know the object's type: we don't want to keep it!
        return False



    def _do_create(self, obj):
        # TODO We could try setting just the .parent relationship and
        # hope the reverse (i.e. the backref) is set up automatically.

        if isinstance(obj, Contest):
            self.contest = obj
        if isinstance(obj, Announcement):
            contest = self.get_object(Contest, obj.contest_id)
            contest.announcements.append(obj)
            contest.announcements.sort(key=lambda a: (a.timestamp))

        if isinstance(obj, Task):
            contest = self.get_object(Contest, obj.contest_id)
            contest.tasks.append(obj)
            contest.tasks.sort(key=lambda a: (a.num))
            # Create child dict in self.submissions and self.user_tests
            for v in self.submissions.itervalues():
                v[obj] = list()
            for v in self.user_tests.itervalues():
                v[obj] = list()
        if isinstance(obj, Statement):
            task = self.get_object(Task, obj.task_id)
            task.statements[obj.language] = obj
        if isinstance(obj, Attachment):
            task = self.get_object(Task, obj.task_id)
            task.attachments[obj.filename] = obj
        if isinstance(obj, SubmissionFormatElement):
            task = self.get_object(Task, obj.task_id)
            task.submission_format.append(obj)

        if isinstance(obj, User):
            contest = self.get_object(Contest, obj.contest_id)
            contest.tasks.append(obj)
            # We DON'T create dict in self.submissions and self.user_tests!
        if isinstance(obj, Message):
            user = self.get_object(User, obj.user_id)
            user.messages.append(obj)
            user.messages.sort(key=lambda a: (a.timestamp))
        if isinstance(obj, Question):
            user = self.get_object(User, obj.user_id)
            user.questions.append(obj)
            user.questions.sort(key=lambda a: (a.question_timestamp, a.reply_timestamp))

        if isinstance(obj, Submission):
            task = self.get_object(Task, obj.task_id)
            user = self.get_object(User, obj.user_id)
            self.submissions[user][task].append(obj)
            self.submissions[user][task].sort(key=lambda a: (a.timestamp))
        if isinstance(obj, Token):
            submission = self.get_object(Submission, obj.submission_id)
            submission.token = obj
        if isinstance(obj, File):
            submission = self.get_object(Submission, obj.submission_id)
            submission.files[obj.filename] = obj

        if isinstance(obj, UserTest):
            task = self.get_object(Task, obj.task_id)
            user = self.get_object(User, obj.user_id)
            self.user_tests[user][task].append(obj)
            self.user_tests[user][task].sort(key=lambda a: (a.timestamp))
        if isinstance(obj, UserTestFile):
            user_test = self.get_object(UserTest, obj.user_test_id)
            user_test.files[obj.filename] = obj
        if isinstance(obj, UserTestManager):
            user_test = self.get_object(UserTest, obj.user_test_id)
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
            contest = self.get_object(Contest, obj.contest_id)
            contest.announcements.remove(obj)

        if isinstance(obj, Task):
            contest = self.get_object(Contest, obj.contest_id)
            contest.tasks.remove(obj)
            # Delete child dict in self.submissions and self.user_tests
            for v in self.submissions.itervalues():
                del v[obj]  # FIXME Do we want to assert its emptiness? (Hint: see deletion order for CASCADES)
            for v in self.user_tests.itervalues():
                del v[obj]  # FIXME Do we want to assert its emptiness? (Hint: see deletion order for CASCADES)
        if isinstance(obj, Statement):
            task = self.get_object(Task, obj.task_id)
            del task.statements[obj.language]
        if isinstance(obj, Attachment):
            task = self.get_object(Task, obj.task_id)
            del task.attachments[obj.filename]
        if isinstance(obj, SubmissionFormatElement):
            task = self.get_object(Task, obj.task_id)
            task.submission_format.remove(obj)

        if isinstance(obj, User):
            contest = self.get_object(Contest, obj.contest_id)
            contest.users.remove(obj)
            # FIXME Should we delete dict in self.submissions and self.user_tests?
        if isinstance(obj, Message):
            user = self.get_object(User, obj.user_id)
            user.messages.remove(obj)
        if isinstance(obj, Question):
            user = self.get_object(User, obj.user_id)
            user.questions.remove(obj)

        if isinstance(obj, Submission):
            # This has to be handled differently
            task = self.get_object(Task, obj.task_id)
            user = self.get_object(User, obj.user_id)
            self.submissions[user][task].remove(obj)
        if isinstance(obj, Token):
            submission = self.get_object(Submission, obj.submission_id)
            submission.token = None
        if isinstance(obj, File):
            submission = self.get_object(Submission, obj.submission_id)
            del submission.files[obj.filename]

        if isinstance(obj, UserTest):
            # This has to be handled differently
            task = self.get_object(Task, obj.task_id)
            user = self.get_object(User, obj.user_id)
            self.user_tests[user][task].remove(obj)
        if isinstance(obj, UserTestFile):
            user_test = self.get_object(UserTest, obj.user_test_id)
            del user_test.files[obj.filename]
        if isinstance(obj, UserTestManager):
            user_test = self.get_object(UserTest, obj.user_test_id)
            del user_test.files[obj.filename]


    def get_contest(self):
        return self.contest


    def get_submissions(self, user, task):
        # FIXME Assert user and task existence?
        if user not in self.submissions:
            submissions = self.session.query(Submission)\
                .filter(Submission.user == user)\
                .order_by(Submission.timestamp)\
                .all()

            self.submissions[user] = dict((task, list()) for task in self.contest.tasks)
            for s in submissions:
                task = self.get_object(Task, s.task_id)
                self.submissions[user][task].append(s)

        return self.submissions[user][task]


    def get_user_tests(self, user, task):
        # FIXME Assert user and task existence?
        if user not in self.user_tests:
            user_tests = self.session.query(UserTest)\
                .filter(UserTest.user == user)\
                .order_by(UserTest.timestamp)\
                .all()

            self.user_tests[user] = dict((task, list()) for task in self.contest.tasks)
            for u in user_tests:
                task = self.get_object(Task, s.task_id)
                self.user_tests[user][task].append(u)

        return self.user_tests[user][task]
