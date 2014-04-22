#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
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

"""Submission-related database interface for SQLAlchemy.

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

from sqlalchemy.schema import Column, ForeignKey, ForeignKeyConstraint, \
    UniqueConstraint, Index
from sqlalchemy.types import Integer, Float, String, Unicode, DateTime
from sqlalchemy.orm import relationship, backref
from sqlalchemy.orm.exc import NoResultFound

from . import Base, User, Task, Dataset, Testcase
from .smartmappedcollection import smart_mapped_collection

from cmscommon.datetime import make_datetime


class UnscoredSubmission(Base):
    __tablename__ = "unscored_submissions"

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # User (id and object) that did the submission.
    user_id = Column(
        Integer,
        ForeignKey(User.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    user = relationship(
        User,
        backref=backref("submissions",
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Task (id and object) of the submission.
    task_id = Column(
        Integer,
        ForeignKey(Task.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    task = relationship(
        Task,
        backref=backref("submissions",
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Whether it's scored or not.
    type_scored = Column(
        Boolean,
        nullable=False)

    __mapper_args__ = {"polymorphic_on": type_scored,
                       "polymorphic_identity": False,
                       "with_polymorphic": "*"}

    # Time of the submission.
    timestamp = Column(
        DateTime,
        nullable=False)

    # Language of submission, or None if not applicable.
    language = Column(
        String,
        nullable=True)

    # Comment from the administrator on the submission.
    comment = Column(
        Unicode,
        nullable=False,
        default="")

    @property
    def short_comment(self):
        """The first line of the comment."""
        return self.comment.split("\n", 1)[0]

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # user_files (dict of UserFile objects indexed by filename)
    # results (list of UnscoredResult or ScoredResult objects)

    def get_result(self, dataset=None):
        """Return the result associated to a dataset.

        dataset (Dataset|None): the dataset for which the caller wants
            the result; if None, the active one is used.

        return (UnscoredResult|None): the result associated to this
            submission and the given dataset, if it exists in the
            database, otherwise None.

        """
        if dataset is None:
            dataset = self.task.active_dataset
        assert self.task == dataset.task

        try:
            return self.sa_session.query(UnscoredResult)\
                .filter(UnscoredResult.submission == self)\
                .filter(UnscoredResult.dataset == dataset).one()
        except NoResultFound:
            return None

    def get_result_or_create(self, dataset=None):
        """Return and, if necessary, create the result for a dataset.

        dataset (Dataset|None): the dataset for which the caller wants
            the result; if None, the active one is used.

        return (ScoredResult): the result associated to the this
            submission and the given dataset; if it does not exists, a
            new one is created.

        """
        if dataset is None:
            dataset = self.task.active_dataset
        assert self.task == dataset.task

        try:
            return self.sa_session.query(UnscoredResult)\
                .filter(UnscoredResult.submission == self)\
                .filter(UnscoredResult.dataset == dataset).one()
        except NoResultFound:
            return UnscoredResult(submission=self, dataset=dataset)


class ScoredSubmission(UnscoredSubmission):
    __tablename__ = "scored_submissions"

    # Auto increment primary key.
    id = Column(
        Integer,
        ForeignKey("unscored_submissions.id"),
        primary_key=True)

    __mapper_args__ = {"polymorphic_identity": True}

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # token (Token object or None)

    def get_result(self, dataset=None):
        """Return the result associated to a dataset.

        dataset (Dataset|None): the dataset for which the caller wants
            the result; if None, the active one is used.

        return (UnscoredResult|None): the result associated to this
            submission and the given dataset, if it exists in the
            database, otherwise None.

        """
        if dataset is None:
            dataset = self.task.active_dataset
        assert self.task == dataset.task

        try:
            return self.sa_session.query(ScoredResult)\
                .filter(Result.submission == self)\
                .filter(Result.dataset == dataset).one()
        except NoResultFound:
            return None

    def get_result_or_create(self, dataset=None):
        """Return and, if necessary, create the result for a dataset.

        dataset (Dataset|None): the dataset for which the caller wants
            the result; if None, the active one is used.

        return (ScoredResult): the result associated to the this
            submission and the given dataset; if it does not exists, a
            new one is created.

        """
        if dataset is None:
            dataset = self.task.active_dataset
        assert self.task == dataset.task

        try:
            return self.sa_session.query(ScoredResult)\
                .filter(Result.submission == self)\
                .filter(Result.dataset == dataset).one()
        except NoResultFound:
            return Result(submission=self, dataset=dataset)

    def tokened(self):
        """Return if the user played a token against the submission.

        return (bool): True if tokened, False otherwise.

        """
        return self.token is not None


class Token(Base):
    """Class to store information about a token.

    """
    __tablename__ = "tokens"
    __table_args__ = (
        UniqueConstraint("submission_id"),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # ScoredSubmission (id and object) the token has been used on.
    submission_id = Column(
        Integer,
        ForeignKey(ScoredSubmission.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    submission = relationship(
        ScoredSubmission,
        backref=backref(
            "token",
            uselist=False,
            cascade="all, delete-orphan",
            passive_deletes=True),
        single_parent=True)

    # Time the token was played.
    timestamp = Column(
        DateTime,
        nullable=False,
        default=make_datetime)


class UnscoredResult(Base):
    """Class to store the evaluation results of a submission.

    """
    __tablename__ = "unscored_results"
    __table_args__ = (
        Index("idx_submission_dataset",
              "submission_id", "dataset_id", unique=True),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # UnscoredSubmission (id and object) this result is for.
    submission_id = Column(
        Integer,
        ForeignKey(UnscoredSubmission.id,
                   onupdate="CASCADE", ondelete="CASCADE"))
    submission = relationship(
        UnscoredSubmission,
        backref=backref(
            "results",
            cascade="all, delete-orphan",
            passive_deletes=True))

    # Dataset (id and object) this result is on.
    dataset_id = Column(
        Integer,
        ForeignKey(Dataset.id,
                   onupdate="CASCADE", ondelete="CASCADE"))
    dataset = relationship(
        Dataset)

    # Whether it's scored or not.
    type_scored = Column(
        Boolean,
        nullable=False)

    __mapper_args__ = {"polymorphic_on": type_scored,
                       "polymorphic_identity": False,
                       "with_polymorphic": "*"}

    # Now below follow the actual result fields.

    # Compilation outcome (can be None = yet to compile, "ok" =
    # compilation successful and we can evaluate, "fail" =
    # compilation unsuccessful, throw it away).
    compilation_outcome = Column(
        String,
        nullable=True)

    # Number of attempts of compilation.
    compilation_tries = Column(
        Integer,
        nullable=False,
        default=0)

    # Evaluation outcome (can be None = yet to evaluate, "ok" =
    # evaluation successful). At any time, this should be equal to
    # evaluations != [].
    evaluation_outcome = Column(
        String,
        nullable=True)

    # Number of attempts of evaluation.
    evaluation_tries = Column(
        Integer,
        nullable=False,
        default=0)

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # compilation_files (list of CompilationFile objects)
    # compilations (list of Compilation objects)
    # executions (list of Execution objects)

    def get_execution(self, testcase):
        """Return Execution of this UsResult on given Testcase, if any

        testcase (Testcase): the testcase the returned execution will
            belong to.
        return (Execution): the (only!) execution of this submission
            result on the given testcase, or None if there isn't any.

        """
        # Use IDs to avoid triggering a lazy-load query.
        assert self.dataset_id == testcase.dataset_id

        # XXX If self.executions is already loaded we can walk over it
        # and spare a query.
        # (We could use .one() and avoid a LIMIT but we would need to
        # catch a NoResultFound exception.)
        self.sa_session.query(Execution)\
            .filter(Execution.submission_result == self)\
            .filter(Execution.codename == testcase.codename)\
            .first()

    def compiled(self):
        """Return whether the submission result has been compiled.

        return (bool): True if compiled, False otherwise.

        """
        return self.compilation_outcome is not None

    def compilation_failed(self):
        """Return whether the submission result did not compile.

        return (bool): True if the compilation failed (in the sense
            that there is a problem in the user's source), False if
            not yet compiled or compilation was successful.

        """
        return self.compilation_outcome == "fail"

    def compilation_succeeded(self):
        """Return whether the submission compiled.

        return (bool): True if the compilation succeeded (in the sense
            that an executable was created), False if not yet compiled
            or compilation was unsuccessful.

        """
        return self.compilation_outcome == "ok"

    def evaluated(self):
        """Return whether the submission result has been evaluated.

        return (bool): True if evaluated, False otherwise.

        """
        return self.evaluation_outcome is not None

    def invalidate_compilation(self):
        """Blank all compilation and evaluation outcomes, and the score.

        """
        self.invalidate_evaluation()
        self.compilation_outcome = None
        self.compilation_tries = 0
        self.compilations = []
        self.compilation_files = []

    def invalidate_evaluation(self):
        """Blank the evaluation outcomes and the score.

        """
        self.invalidate_score()
        self.evaluation_outcome = None
        self.evaluation_tries = 0
        self.executions = []

    def set_compilation_outcome(self, success):
        """Set the compilation outcome based on the success.

        success (bool): if the compilation was successful.

        """
        self.compilation_outcome = "ok" if success else "fail"

    def set_evaluation_outcome(self):
        """Set the evaluation outcome (always ok now).

        """
        self.evaluation_outcome = "ok"


class ScoredResult(UnscoredResult):
    __tablename__ = "scored_results"

    # Auto increment primary key.
    id = Column(
        Integer,
        ForeignKey("unscored_results.id"),
        primary_key=True)

    __mapper_args__ = {"polymorphic_identity": True}

    # Score as computed by ScoringService. Null means not yet scored.
    score = Column(
        Float,
        nullable=True)

    # Score details. It's a JSON-encoded string containing information
    # that is given to ScoreType.get_html_details to generate an HTML
    # snippet that is shown on AWS and, if the user used a token, on
    # CWS to display the details of the submission.
    # For example, results for each testcases, subtask, etc.
    score_details = Column(
        String,
        nullable=True)

    # The same as the last two fields, but from the point of view of
    # the user (when he/she did not play a token).
    public_score = Column(
        Float,
        nullable=True)
    public_score_details = Column(
        String,
        nullable=True)

    # Ranking score details. It is a list of strings that are going to
    # be shown in a single row in the table of submission in RWS. JSON
    # encoded.
    ranking_score_details = Column(
        String,
        nullable=True)

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # evaluations (list of Evaluation objects)

    def get_evaluation(self, testcase):
        """Return Evaluation of this Result on given Testcase, if any

        testcase (Testcase): the testcase the returned evaluation will
            belong to.
        return (Evaluation): the (only!) evaluation of this submission
            result on the given testcase, or None if there isn't any.

        """
        # Use IDs to avoid triggering a lazy-load query.
        assert self.dataset_id == testcase.dataset_id

        # XXX If self.evaluations is already loaded we can walk over it
        # and spare a query.
        # (We could use .one() and avoid a LIMIT but we would need to
        # catch a NoResultFound exception.)
        self.sa_session.query(Evaluation)\
            .filter(Evaluation.submission_result == self)\
            .filter(Evaluation.codename == testcase.codename)\
            .first()

    def needs_scoring(self):
        """Return whether the submission result needs to be scored.

        return (bool): True if in need of scoring, False otherwise.

        """
        return (self.compilation_failed() or self.evaluated()) and \
            not self.scored()

    def scored(self):
        """Return whether the submission result has been scored.

        return (bool): True if scored, False otherwise.

        """
        return all(getattr(self, k) is not None for k in [
            "score", "score_details",
            "public_score", "public_score_details",
            "ranking_score_details"])

    def invalidate_evaluation(self):
        """Blank the evaluation outcomes and the score.

        """
        self.invalidate_score()
        self.evaluation_outcome = None
        self.evaluation_tries = 0
        self.executions = []
        self.evaluations = []

    def invalidate_score(self):
        """Blank the score.

        """
        self.score = None
        self.score_details = None
        self.public_score = None
        self.public_score_details = None
        self.ranking_score_details = None


class Compilation(Base):
    __tablename__ = "compilations"
    __table_args__ = (
        UniqueConstraint("result_id", "codename"),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # UnscoredResult (id and object) owning the compilation.
    result_id = Column(
        Integer,
        ForeignKey(UnscoredResult.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    result = relationship(
        UnscoredResult,
        backref=backref("compilations",
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Codename identifying the compilation.
    codename = Column(
        Unicode,
        nullable=False)

    # String containing output from the sandbox.
    text = Column(
        String,
        nullable=True)

    # The compiler stdout and stderr.
    stdout = Column(
        Unicode,
        nullable=True)
    stderr = Column(
        Unicode,
        nullable=True)

    # Other information about the compilation.
    time = Column(
        Float,
        nullable=True)
    wall_clock_time = Column(
        Float,
        nullable=True)
    memory = Column(
        Integer,
        nullable=True)

    # Worker shard and sandbox where the compilation was performed.
    shard = Column(
        Integer,
        nullable=True)
    sandbox = Column(
        Unicode,
        nullable=True)


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("result_id", "codename"),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # UnscoredResult (id and object) owning the execution.
    result_id = Column(
        Integer,
        ForeignKey(UnscoredResult.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    result = relationship(
        UnscoredResult,
        backref=backref("executions",
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Codename identifying the execution.
    codename = Column(
        Unicode,
        nullable=False)

    # Whether it's scored (that is, an Evaluation) or not (that is,
    # just an Execution).
    type_scored = Column(
        Boolean,
        nullable=False)

    __mapper_args__ = {"polymorphic_on": type_scored,
                       "polymorphic_identity": False,
                       "with_polymorphic": "*"}

    # String containing output from the grader (usually "Correct",
    # "Time limit", ...).
    text = Column(
        String,
        nullable=True)

    # Evaluation's time and wall-clock time, in seconds.
    time = Column(
        Float,
        nullable=True)
    wall_clock_time = Column(
        Float,
        nullable=True)

    # Memory used by the evaluation, in bytes.
    memory = Column(
        Integer,
        nullable=True)

    # Worker shard and sandbox where the evaluation was performed.
    shard = Column(
        Integer,
        nullable=True)
    sandbox = Column(
        Unicode,
        nullable=True)

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # execution_files (list of ExecutionFile objects)


class Evaluation(Execution):
    __tablename__ = "evaluations"

    # Auto increment primary key.
    id = Column(
        Integer,
        ForeignKey("executions.id"),
        primary_key=True)

    __mapper_args__ = {"polymorphic_identity": True}

    # String containing the outcome of the evaluation (usually 1.0,
    # ...) not necessary the points awarded, that will be computed by
    # the score type.
    outcome = Column(
        Unicode,
        nullable=True)
