#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2013 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2013 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
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

"""The service that forwards data to RankingWebServer.

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import json
import logging
import string

import gevent
import gevent.queue

import requests
import requests.exceptions
from urlparse import urljoin, urlsplit

from cms import config
from cms.io import Service, rpc_method
from cms.db import SessionGen, Contest, User, Task, Submission, \
    SubmissionResult, Token, Watcher, get_contest_list
from cms.grading.scoretypes import get_score_type
from cmscommon.datetime import make_timestamp


logger = logging.getLogger(__name__)


class CannotSendError(Exception):
    pass


def encode_id(entity_id):
    """Encode the id using only A-Za-z0-9_.

    entity_id (unicode): the entity id to encode.
    return (unicode): encoded entity id.

    """
    encoded_id = ""
    for char in entity_id.encode('utf-8'):
        if char not in string.ascii_letters + string.digits:
            encoded_id += "_%x" % ord(char)
        else:
            encoded_id += unicode(char)
    return encoded_id


def safe_put_data(ranking, resource, data, operation):
    """Send some data to ranking using a PUT request.

    ranking (bytes): the URL of ranking server.
    resource (bytes): the relative path of the entity.
    data (dict): the data to JSON-encode and send.
    operation (unicode): a human-readable description of the operation
        we're performing (to produce log messages).

    raise (CannotSendError): in case of communication errors.

    """
    try:
        url = urljoin(ranking, resource)
        # XXX With requests-1.2 auth is automatically extracted from
        # the URL: there is no need for this.
        auth = urlsplit(url)
        res = requests.put(url, json.dumps(data, encoding="utf-8"),
                           auth=(auth.username, auth.password),
                           headers={'content-type': 'application/json'},
                           verify=config.https_certfile)
    except requests.exceptions.RequestException as error:
        msg = "%s while %s: %s." % (type(error).__name__, operation, error)
        logger.warning(msg)
        raise CannotSendError(msg)
    if 400 <= res.status_code < 600:
        msg = "Status %s while %s." % (res.status_code, operation)
        logger.warning(msg)
        raise CannotSendError(msg)


class RankingProxy(object):

    """A thread that sends data to one ranking.

    The object is used as a thread-local storage and its run method is
    the function that, started as a greenlet, uses it.

    It maintains a queue of data to send. At each "round" the queue is
    emptied (i.e. all jobs are fetched) and the data is then "combined"
    to minimize the number of actual HTTP requests: they'll be at most
    one per entity type.

    Each entity type is identified by a integral class-level constant.

    """

    # We use a single queue for all the data we have to send to the
    # ranking so we need to distingush the type of each item.
    CONTEST_TYPE = 0
    TASK_TYPE = 1
    TEAM_TYPE = 2
    USER_TYPE = 3
    SUBMISSION_TYPE = 4
    SUBCHANGE_TYPE = 5

    # The resource paths for the different entity types, relative to
    # the self.ranking URL.
    RESOURCE_PATHS = [
        b"contests",
        b"tasks",
        b"teams",
        b"users",
        b"submissions",
        b"subchanges"]

    # How many different entity types we know about.
    TYPE_COUNT = len(RESOURCE_PATHS)

    # How long we wait after having failed to push data to a ranking
    # before trying again.
    FAILURE_WAIT = 60.0

    def __init__(self, ranking):
        """Create a proxy for the ranking at the given URL.

        ranking (bytes): a complete URL (containing protocol, username,
            password, hostname, port and prefix) where a ranking is
            supposed to listen.

        """
        self.ranking = ranking
        self.data_queue = gevent.queue.JoinableQueue()

    def run(self):
        """Consume (i.e. send) the data put in the queue, forever.

        Pick all operations found in the queue (if there aren't any,
        block waiting until there are), combine them and send HTTP
        requests to the target ranking. Do it until something very bad
        happens (i.e. some exception is raised). If communication fails
        don't stop, just wait FAILURE_WAIT seconds before restarting
        the loop.

        Do all this cooperatively: yield at every blocking operation
        (queue fetch, request send, failure wait, etc.). Since the
        queue is joinable, also notify when the fetched jobs are done.

        """
        # The cumulative data that we will try to send to the ranking,
        # built by combining items in the queue.
        data = list(dict() for i in xrange(self.TYPE_COUNT))

        # The number of times we will call self.data_queue.task_done()
        # after a successful send (i.e. how many times we called .get()
        # on the queue to build up the data we have now).
        task_count = list(0 for i in xrange(self.TYPE_COUNT))

        while True:
            # If we don't have anything left to do, block until we get
            # something new.
            if sum(task_count) == 0:
                self.data_queue.peek()

            try:
                while True:
                    # Get other data if it's immediately available.
                    item = self.data_queue.get_nowait()
                    task_count[item[0]] += 1

                    # Merge this item with the cumulative data.
                    data[item[0]].update(item[1])
            except gevent.queue.Empty:
                pass

            try:
                for i in xrange(self.TYPE_COUNT):
                    # Send entities of type i.
                    if len(data[i]) > 0:
                        # XXX We abuse the resource path as the english
                        # (plural) name for the entity type.
                        name = self.RESOURCE_PATHS[i]
                        operation = \
                            "sending %s to ranking %s" % (name, self.ranking)

                        logger.debug(operation.capitalize())
                        safe_put_data(
                            self.ranking, b"%s/" % name, data[i], operation)

                        data[i].clear()
                        for _ in xrange(task_count[i]):
                            self.data_queue.task_done()
                        task_count[i] = 0

            except CannotSendError:
                # A log message has already been produced.
                gevent.sleep(self.FAILURE_WAIT)
            except:
                # Whoa! That's unexpected!
                logger.error("Unexpected error.", exc_info=True)
                gevent.sleep(self.FAILURE_WAIT)


class ProxyService(Service):

    """Maintain the information held by rankings up-to-date.

    Discover (by receiving notifications and by periodically sweeping
    over the database) when relevant data changes happen and forward
    them to the rankings by putting them in the queues of the proxies.

    The "entry points" are submission_scored, submission_tokened,
    dataset_updated and search_jobs_not_done. They can all be called
    via RPC and the latter is also periodically executed (each
    JOBS_NOT_DONE_CHECK_TIME). These methods fetch objects from the
    database, check their validity (existence, non-hiddenness, etc.)
    and status and, if needed, put call initialize, send_score and
    send_token that construct the data to send to rankings and put it
    in the queues of all proxies.

    """

    # How often we look for submission not scored/tokened.
    JOBS_NOT_DONE_CHECK_TIME = 347.0

    def __init__(self, shard):
        """Start the service with the given parameters.

        Create an instance of the ProxyService and make it listen on
        the address corresponding to the given shard.

        shard (int): the shard of the service, i.e. this instance
            corresponds to the shard-th entry in the list of addresses
            (hostname/port pairs) for this kind of service in the
            configuration file.

        """
        Service.__init__(self, shard)

        # Store what data we already sent to rankings.
        self.contests_sent = dict()
        self.users_sent = dict()
        self.tasks_sent = dict()
        self.scores_sent = dict()
        self.tokens_sent = dict()

        # Create and spawn threads to send data to rankings.
        self.rankings = list()
        for ranking in config.rankings:
            proxy = RankingProxy(ranking.encode('utf-8'))
            gevent.spawn(proxy.run)
            self.rankings.append(proxy)

        # Obtain a Watcher and attach callbacks to it.
        self.watcher = Watcher(self.initialize)

        # self.watcher.listen(lambda id_, *args: self.
        #                     Watcher.EVENT_CREATE, Contest)
        self.watcher.listen(lambda id_, *args: self.contest_created(id_),
                            Watcher.EVENT_UPDATE, Contest,
                            "name", "description", "start", "stop", "score_precision")
        # self.watcher.listen(lambda id_, *args: self.
        #                     Watcher.EVENT_DELETE, Contest)

        self.watcher.listen(lambda id_, *args: self.user_created(id_),
                            Watcher.EVENT_CREATE, User)
        self.watcher.listen(lambda id_, *args: self.user_created(id_),
                            Watcher.EVENT_UPDATE, User,
                            "username", "first_name", "last_name")
        # self.watcher.listen(lambda id_, *args: self.
        #                     Watcher.EVENT_DELETE, User)

        # self.watcher.listen(lambda id_, *args: self.
        #                     Watcher.EVENT_UPDATE, User, "rws_hidden")

        self.watcher.listen(lambda id_, *args: self.task_created(id_),
                            Watcher.EVENT_CREATE, Task)
        self.watcher.listen(lambda id_, *args: self.task_created(id_),
                            Watcher.EVENT_UPDATE, Task,
                            "contest_id", "name", "title", "num", "score_precision")
        # self.watcher.listen(lambda id_, *args: self.
        #                     Watcher.EVENT_DELETE, Task)

        self.watcher.listen(lambda id_, *args: self....
                            Watcher.EVENT_CREATE, Submission)
        self.watcher.listen(lambda id_, *args: self....
                            Watcher.EVENT_UPDATE, Submission,
                            "user_id", "task_id", "timestamp")
        # self.watcher.listen(lambda id_, *args: self.
        #                     Watcher.EVENT_DELETE, Submission)

        self.watcher.listen(lambda id_, *args: self....
                            Watcher.EVENT_CREATE, SubmissionResult)
        self.watcher.listen(lambda id_, *args: self....
                            Watcher.EVENT_UPDATE, SubmissionResult,
                            "submission_id", "dataset_id", "score", "ranking_score_details")
        # self.watcher.listen(lambda id_, *args: self.
        #                     Watcher.EVENT_DELETE, SubmissionResult)

        # XXX SubmissionResult.dataset_id

        self.watcher.listen(lambda id_, *args: self....
                            Watcher.EVENT_CREATE, Token)
        self.watcher.listen(lambda id_, *args: self....
                            Watcher.EVENT_UPDATE, Token,
                            "submission_id", "timestamp")
        # self.watcher.listen(lambda id_, *args: self.
        #                     Watcher.EVENT_DELETE, Token)

        lambda x, *args: x

    def initialize(self):
        """Send to all the rankings all the data that are supposed to be
        sent before the contest: contest, users, tasks. No support for
        teams, flags and faces.

        """
        logger.info("Initializing rankings.")

        with SessionGen() as session:
            for contest in get_contest_list(session):
                if contest.rws_hidden:
                    continue

                self.send_contest(contest)

                for user in contest.users:
                    if user.rws_hidden:
                        continue

                    self.send_user(user)

                for task in contest.tasks:
                    if task.rws_hidden:
                        continue

                    self.send_task(task)

    def send_contest(self, contest):
        # Data to send to remote rankings.
        contest_id = encode_id(contest.name)
        contest_data = {
            "name": contest.description,
            "begin": int(make_timestamp(contest.start)),
            "end": int(make_timestamp(contest.stop)),
            "score_precision": contest.score_precision}

        # Adding operations to the queue.
        ranking.data_queue.put((ranking.CONTEST_TYPE,
                                {contest_id: contest_data}))

    def send_user(self, user):
        # Data to send to remote rankings.
        user_id = encode_id(user.username)
        user_data = {
            "f_name": user.first_name,
            "l_name": user.last_name,
            "team": None}

        # Adding operations to the queue.
        ranking.data_queue.put((ranking.USER_TYPE,
                                {user_id: user_data}))

    def send_task(self, task):
        # Data to send to remote rankings.
        task_id = encode_id(task.name)
        task_data = {
            "short_name": task.name
            "name": task.title,
            "contest": encode_id(user.contest.name),
            "order": task.num,
            "max_score": 100.0,
            "extra_headers": [],
            "score_precision": task.score_precision}

        # Adding operations to the queue.
        ranking.data_queue.put((ranking.TASK_TYPE,
                                {task_id: task_data}))

    def send_score(self, submission):
        """Send the score for the given submission to all rankings.

        Put the submission and its score subchange in all the proxy
        queues for them to be sent to rankings.

        """
        submission_result = submission.get_result()

        # Data to send to remote rankings.
        submission_id = str(submission.id)
        submission_data = {
            "user": encode_id(submission.user.username),
            "task": encode_id(submission.task.name),
            "time": int(make_timestamp(submission.timestamp))}

        subchange_id = "%d%ss" % (make_timestamp(submission.timestamp),
                                  submission_id)
        subchange_data = {
            "submission": submission_id,
            "time": int(make_timestamp(submission.timestamp))}

        # XXX This check is probably useless.
        if submission_result is not None and submission_result.scored():
            # We're sending the unrounded score to RWS
            subchange_data["score"] = submission_result.score
            subchange_data["extra"] = \
                json.loads(submission_result.ranking_score_details)

        # Adding operations to the queue.
        for ranking in self.rankings:
            ranking.data_queue.put((ranking.SUBMISSION_TYPE,
                                    {submission_id: submission_data}))
            ranking.data_queue.put((ranking.SUBCHANGE_TYPE,
                                    {subchange_id: subchange_data}))

        self.scores_sent_to_rankings.add(submission.id)

    def send_token(self, submission):
        """Send the token for the given submission to all rankings.

        Put the submission and its token subchange in all the proxy
        queues for them to be sent to rankings.

        """
        # Data to send to remote rankings.
        submission_id = str(submission.id)
        submission_data = {
            "user": encode_id(submission.user.username),
            "task": encode_id(submission.task.name),
            "time": int(make_timestamp(submission.timestamp))}

        subchange_id = "%d%st" % (make_timestamp(submission.token.timestamp),
                                  submission_id)
        subchange_data = {
            "submission": submission_id,
            "time": int(make_timestamp(submission.token.timestamp)),
            "token": True}

        # Adding operations to the queue.
        for ranking in self.rankings:
            ranking.data_queue.put((ranking.SUBMISSION_TYPE,
                                    {submission_id: submission_data}))
            ranking.data_queue.put((ranking.SUBCHANGE_TYPE,
                                    {subchange_id: subchange_data}))

        self.tokens_sent_to_rankings.add(submission.id)

    @rpc_method
    def reinitialize(self):
        """Repeat the initialization procedure for all rankings.

        This method is usually called via RPC when someone knows that
        some basic data (i.e. contest, tasks or users) changed and
        rankings need to be updated.

        """
        logger.info("Reinitializing rankings.")
        self.initialize()

    def contest_created(self, contest_id):
        with SessionGen(commit=False) as session:
            contest = Contest.get_from_id(contest_id, session)

            if contest is None:
                logger.error("Asked to send non-existent contest.")
                raise ValueError

            if not contest.rws_hidden:
                self.send_contest(contest)

    def user_created(self, user_id):
        with SessionGen(commit=False) as session:
            user = User.get_from_id(user_id, session)

            if user is None:
                logger.error("Asked to send non-existent user.")
                raise ValueError

            if not user.rws_hidden:
                self.send_user(user)

    def task_created(self, task_id):
        with SessionGen(commit=False) as session:
            task = Task.get_from_id(task_id, session)

            if task is None:
                logger.error("Asked to send non-existent task.")
                raise ValueError

            if not task.rws_hidden:
                self.send_task(task)

    @rpc_method
    def submission_scored(self, submission_id):
        """Notice that a submission has been scored.

        Usually called by ScoringService when it's done with scoring a
        submission result. Since we don't trust anyone we verify that,
        and then send data about the score to the rankings.

        submission_id (int): the id of the submission that changed.
        dataset_id (int): the id of the dataset to use.

        """
        with SessionGen() as session:
            submission = Submission.get_from_id(submission_id, session)

            if submission is None:
                logger.error("[submission_scored] Received score request for "
                             "unexistent submission id %s." % submission_id)
                raise KeyError("Submission not found.")

            if submission.user.rws_hidden:
                logger.info("[submission_scored] Score for submission %d "
                            "not sent because user is hidden." % submission_id)
                return

            if submission.task.rws_hidden:
                logger.info("[submission_scored] Score for submission %d "
                            "not sent because task is hidden." % submission_id)
                return

            if submission.task.contest.rws_hidden:
                logger.info("[submission_scored] Score for submission %d "
                            "not sent because contest is hidden." % submission_id)
                return

            # Update RWS.
            self.send_score(submission)

    @rpc_method
    def submission_tokened(self, submission_id):
        """Notice that a submission has been tokened.

        Usually called by ContestWebServer when it's processing a token
        request of an user. Since we don't trust anyone we verify that,
        and then send data about the token to the rankings.

        submission_id (int): the id of the submission that changed.

        """
        with SessionGen() as session:
            submission = Submission.get_from_id(submission_id, session)

            if submission is None:
                logger.error("[submission_tokened] Received token request for "
                             "unexistent submission id %s." % submission_id)
                raise KeyError("Submission not found.")

            if submission.user.rws_hidden:
                logger.info("[submission_tokened] Token for submission %d "
                            "not sent because user is hidden." % submission_id)
                return

            if submission.task.rws_hidden:
                logger.info("[submission_tokened] Token for submission %d "
                            "not sent because task is hidden." % submission_id)
                return

            if submission.task.contest.rws_hidden:
                logger.info("[submission_tokened] Token for submission %d "
                            "not sent because contest is hidden." % submission_id)
                return

            # Update RWS.
            self.send_token(submission)

    @rpc_method
    def dataset_updated(self, task_id):
        """Notice that the active dataset of a task has been changed.

        Usually called by AdminWebServer when the contest administrator
        changed the active dataset of a task. This means that we should
        update all the scores for the task using the submission results
        on the new active dataset. If some of them are not available
        yet we keep the old scores (we don't delete them!) and wait for
        ScoringService to notify us that the new ones are available.

        task_id (int): the ID of the task whose dataset has changed.

        """
        with SessionGen() as session:
            task = Task.get_from_id(task_id, session)
            dataset = task.active_dataset

            if task.rws_hidden or task.contest.rws_hidden:
                return

            logger.info("Dataset update for task %d (dataset now is %d)." % (
                task.id, dataset.id))

            # max_score and/or extra_headers might have changed.
            self.reinitialize()

            for submission in task.submissions:
                # Update RWS.
                if not submission.user.rws_hidden and \
                        submission.get_result().scored():
                    self.send_score(submission)
