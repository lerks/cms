#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

from __future__ import absolute_import
from __future__ import unicode_literals

from sqlalchemy.schema import Column, ForeignKey, ForeignKeyConstraint, \
    UniqueConstraint
from sqlalchemy.types import Boolean, Integer, String, Unicode, Enum
from sqlalchemy.orm import relationship, backref

from . import Base, Submission, Dataset, SubmissionResult, Testcase, Evaluation
from .smartmappedcollection import smart_mapped_collection

from cms import LANGUAGES


class FileSchema(Base):
    __tablename__ = "file_schemas"
    __table_args__ = (
        UniqueConstraint("dataset_id", "language", "codename"),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    type = Column(
        Enum("user", "dataset", "compilation", "testcase", "execution",
             name="file_schema_type"),
        nullable=False,
        default="user"
    )

    __mapper_args__ = {
        "polymorphic_on": type,
        "polymorphic_identity": "user"
    }

    # Dataset (just the id) owning the file schema.
    dataset_id = Column(
        Integer,
        ForeignKey(Dataset.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    # We cannot add the relationship because we cannot set the backref
    # or back_populates, as we want each subclass to have its own.

    # Language and codename identifying the file.
    language = Column(
        Enum(*LANGUAGES, name="language"),
        nullable=True)
    codename = Column(
        Unicode,
        nullable=False)

    # Filename, maximum allowed size and optional flag values
    # overriding the defaults provided by the TaskType.
    filename = Column(
        Unicode,
        nullable=False)
    max_size = Column(
        Integer,
        nullable=True)
    optional = Column(
        Boolean,
        nullable=False)


class UserFileSchema(FileSchema):
    __mapper_args__ = {
        "polymorphic_identity": "user"
    }

    # Dataset (just the object) owning the file schema.
    dataset = relationship(
        Dataset,
        backref=backref("user_file_schemas",
                        cascade="all, delete-orphan",
                        passive_deletes=True))


class DatasetFileSchema(FileSchema):
    __mapper_args__ = {
        "polymorphic_identity": "dataset"
    }

    # Dataset (just the object) owning the file schema.
    dataset = relationship(
        Dataset,
        backref=backref("dataset_file_schemas",
                        cascade="all, delete-orphan",
                        passive_deletes=True))


class CompilationFileSchema(FileSchema):
    __mapper_args__ = {
        "polymorphic_identity": "compilation"
    }

    # Dataset (just the object) owning the file schema.
    dataset = relationship(
        Dataset,
        backref=backref("compilation_file_schemas",
                        cascade="all, delete-orphan",
                        passive_deletes=True))


class TestcaseFileSchema(FileSchema):
    __mapper_args__ = {
        "polymorphic_identity": "testcase"
    }

    # Dataset (just the object) owning the file schema.
    dataset = relationship(
        Dataset,
        backref=backref("testcase_file_schemas",
                        cascade="all, delete-orphan",
                        passive_deletes=True))


class ExecutionFileSchema(FileSchema):
    __mapper_args__ = {
        "polymorphic_identity": "execution"
    }

    # Dataset (just the object) owning the file schema.
    dataset = relationship(
        Dataset,
        backref=backref("execution_file_schemas",
                        cascade="all, delete-orphan",
                        passive_deletes=True))


class UserFile(Base):
    __tablename__ = "user_files"
    __table_args__ = (
        UniqueConstraint("submission_id", "filename"),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Submission (id and object) owning the file.
    submission_id = Column(
        Integer,
        ForeignKey(Submission.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    submission = relationship(
        Submission,
        backref=backref("user_files",
                        collection_class=smart_mapped_collection("filename"),
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Filename identifying the file.
    filename = Column(
        Unicode,
        nullable=False)

    # Digest of the file provided by the user.
    digest = Column(
        String,
        nullable=False)


class DatasetFile(Base):
    __tablename__ = "dataset_files"
    __table_args__ = (
        UniqueConstraint("dataset_id", "language", "codename"),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Dataset (id and object) owning the file.
    dataset_id = Column(
        Integer,
        ForeignKey(Dataset.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    dataset = relationship(
        Dataset,
        backref=backref("dataset_files",
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Language and codename identifying the file.
    language = Column(
        Enum(*LANGUAGES, name="language"),
        nullable=True)
    codename = Column(
        Unicode,
        nullable=False)

    # Digest of the file provided by the admin.
    digest = Column(
        String,
        nullable=False)


class CompilationFile(Base):
    __tablename__ = "compilation_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ("submission_id", "dataset_id"),
            (SubmissionResult.submission_id, SubmissionResult.dataset_id),
            onupdate="CASCADE", ondelete="CASCADE"),
        UniqueConstraint("submission_id", "dataset_id", "codename"),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Submission (id and object) owning the file.
    submission_id = Column(
        Integer,
        ForeignKey(Submission.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    submission = relationship(
        Submission)

    # Dataset (id and object) owning the file.
    dataset_id = Column(
        Integer,
        ForeignKey(Dataset.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    dataset = relationship(
        Dataset)

    # SubmissionResult owning the file.
    submission_result = relationship(
        SubmissionResult,
        backref=backref("compilation_files",
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Codename identifying the file.
    codename = Column(
        Unicode,
        nullable=False)

    # Digest of the autogenerated file.
    digest = Column(
        String,
        nullable=False)


class TestcaseFile(Base):
    __tablename__ = "testcase_files"
    __table_args__ = (
        UniqueConstraint("testcase_id", "language", "codename"),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Testcase (id and object) owning the file.
    testcase_id = Column(
        Integer,
        ForeignKey(Testcase.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    testcase = relationship(
        Testcase,
        backref=backref("testcase_files",
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Language and codename identifying the file.
    language = Column(
        Enum(*LANGUAGES, name="language"),
        nullable=True)
    codename = Column(
        Unicode,
        nullable=False)

    # Digest of the file provided by the admin.
    digest = Column(
        String,
        nullable=False)


class ExecutionFile(Base):
    __tablename__ = "execution_files"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "codename"),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Evaluation (id and object) owning the file.
    evaluation_id = Column(
        Integer,
        ForeignKey(Evaluation.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    evaluation = relationship(
        Evaluation,
        backref=backref("evaluation_files",
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Codename identifying the file.
    codename = Column(
        Unicode,
        nullable=False)

    # Digest of the autogenerated file.
    digest = Column(
        String,
        nullable=False)
