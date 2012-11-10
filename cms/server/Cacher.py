from sqlalchemy.engine.url import make_url

import psycopg2
import psycopg2.extensions

from cms.db.SQLALchemyAll import Session, \
    Contest, Announcement, \
    Task, Statement, Attachment, SubmissionFormatElement, \
    User, Message, Question, \
    Submission, Token, File, \
    UserTest, UserTestFile

from sqlalchemy.orm.util import identity_key

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
        self.pg_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

        cursor = self.pg_conn.cursor()
        cursor.execute("LISTEN create;")
        cursor.execute("LISTEN update;")
        cursor.execute("LISTEN delete;")

        self.io_loop = io_loop or tornado.ioloop.IOLoop.instance()
        self.io_loop.add_handler(self.pg_conn.fileno(), self._callback, self.io_loop.READ)

        self.session = Session(autocommit=True)
        self.objects = dict()

        # AHAHAH!!! Very funny!
        self.contest_id = contest_id
        self.contest = Contest.get_from_id(contest_id, self.session)
        self.tasks = dict((t.name, t) for t in self.contest.tasks)
        self.users = dict((u.username, u) for u in self.contest.users)
        self.submissions = dict()

    def __del__(self):
        self.io_loop.remove_handler(self.pg_conn.fileno())

        # We could close the PostgreSQL connection by explictly calling
        # its .close() method, but we rely on it being deleted by the
        # garbage collector and closed by its __del__ method.


    def get_contest(self):
        return self.contest

    def get_task(self, taskname):
        # FIXME Raise some error
        return self.tasks[taksname]

    def get_user(self, username):
        # FIXME Raise some error
        return self.users[username]

    def get_submissions(self, username, taskname=None):
        if username not in self.submissions:
            self.submissions[username] = dict()
            for s in self.users[username].submissions:
                self.submissions[username].setdefault(s.task.name, []).append(s)
            for t in self.tasks:
                self.submissions[username][t.name].sort(key=lambda s: s.timestamp)

        if taskname is None:
            return self.submissions[username]
        else:
            return self.submissions[username][taskname]

    def _callback(self, fd, events):
        # TODO Hmm... could this raise an exception in case some error happened?
        # (like... the server died, our connection broke, etc.)
        self.pg_conn.poll()

        print type(self.pg_conn.notifies)
        while self.pg_conn.notifies:
            notify = self.pg_conn.notifies.pop()

            # FIXME Can we use notify.pid somehow?
            event = notify.channel
            table, _tmp, id_ = notify.payload.rpartition(' ')
            id_ = int(id_)

            # TODO fuck
            cls = {"contests": Contest,
                   "tasks": Task,
                   "users": User,
                   "submissions": Submission}[table]
            key = identity_key(cls, id_)

            old_obj = self.objects.get(key, None)

            if event == "create" or event == "update":
                new_obj = cls.get_from_id(id_, self.session)
                if not self._want_to_keep(new_obj):
                    new_obj = None

                if self._want_to_keep(new_obj):
                    if old_obj is not None:
                        # UPDATE
                        pass
                    else:
                        # CREATE
                        pass
                else:
                    event = "delete"

            elif event == "delete":
                if old_obj is not None:
                    # DELETE
                    pass
                else:
                    # Nothing to be done
                    pass

            else:
                raise RuntimeError("Unknown event '%s'" % event)


    def _want_to_keep(self, obj):
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
        # FIXME SubmissionFormatElement
        if isinstance(obj, User):
            # Only if we are already tracking it
            # FIXME Explain better
            return identity_key(User, obj.id) in self.objects
        if isinstance(obj, Message):
            return identity_key(User, obj.user_id) in self.objects
        if isinstance(obj, Question):
            return identity_key(User, obj.user_id) in self.objects
        if isinstance(obj, Submission):
            return identity_key(User, obj.user_id) in self.objects
        if isinstance(obj, Token):
            return identity_key(Submission, obj.submission_id) in self.objects
        if isinstance(obj, File):
            return identity_key(Submission, obj.submission_id) in self.objects
        if isinstance(obj, UserTest):
            # Only if we are already tracking it
            # FIXME Explain better
            return identity_key(User, obj.user_id) in self.objects
        if isinstance(obj, UserTestFile):
            return identity_key(UserTest, obj.user_test_id) in self.objects

        raise RuntimeError("Unknown type '%s'" % type(obj).__name__)



    def handle_create(self, new_obj):
        pass

    def handle_update(self, old_obj, new_obj):
        pass

    def handle_delete(self, old_obj):
        pass

    def _check_internal_state(self):
        pass

