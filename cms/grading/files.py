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
from __future__ import print_function

import logging
from collections import namedtuple

from cms.grading.tasktypes import get_task_type


logger = logging.getLogger(__name__)


FileSchema = namedtuple("FileSchema", ["filename", "max_size", "optional"])
File = namedtuple("File", ["filename", "digest"])


def copy_schemas(schemas):
    return {k: FileSchema(v.filename, v.max_size, v.optional)
            for k, v in schemas.iteritems()}


def filter_schemas_by_language(schemas, language, operation):
    result = {}

    for schema in schemas:
        if schema.language is None:
            result[schema.codename] = schema

    if language is not None:
        for schema in schemas:
            if schema.language == language:
                if schema.codename in result:
                    logger.error("Schemas codenamed %r (%s) conflicted when "
                                 "preparing %s.", schema.codename, language,
                                 operation)
                    raise ValueError("Codename %r (%s) conflicts." %
                                     (schema.codename, language))
                else:
                    result[schema.codename] = schema

    # We copy because the arguments were most probably instances of
    # database classes, but we want to return tuples.
    return copy_schemas(result)


def override_schemas(default, override, operation):
    result = {}

    for codename, schema in default.iteritems():
        result[codename] = schema

    for codename, schema in override.iteritems():
        if codename in result:
            result[codename] = FileSchema(
                schema.filename, schema.max_size,
                schema.optional and result[codename].optional)
        else:
            logger.warning("Schema codenamed %r was useless at overriding "
                           "when preparing %s.", codename, operation)

    return result


def map_filenames_to_codenames(schemas, operation):
    result = {}

    for codename, schema in schemas.iteritems():
        if schema.filename in result:
            logger.error("Schemas filenamed %r conflicted when preparing %s.",
                         schema.filename, operation)
            raise ValueError("Filename %r conflicts." % schema.filename)
        else:
            result[schema.filename] = codename


def match_user_files_to_codenames(codenames, files, operation):
    result = {}

    for filename, file_ in files.iteritems():
        if filename in codenames:
            result[codenames[filename]] = file_
        else:
            logger.warning("User file filenamed %r didn't get matched to any "
                           "codename when preparing %s.", filename, operation)

    return result


def merge_schemas_sets(schemas_sets, operation):
    result = {}

    for schemas in schemas_sets:
        for codename, schema in schemas.iteritems():
            if codename in result:
                logger.error("Schemas codenamed %r conflicted when preparing "
                             "%s.", codename, operation)
                raise ValueError("Codename %r conflicts." % codename)
            else:
                result[codename] = schema

    return result


def filter_files_by_language(files, language, operation):
    result = {}

    for file_ in files:
        if file_.language is None:
            result[file_.codename] = file_

    if language is not None:
        for file_ in files:
            if file_.language == language:
                if file_.codename in result:
                    logger.error("Files codenamed %r (%s) conflicted when "
                                 "preparing %s.", file_.codename, language,
                                 operation)
                    raise ValueError("Codename %r (%s) conflicts." %
                                     (file_.codename, language))
                else:
                    result[file_.codename] = file_

    return result


def merge_file_sets(file_sets, operation):
    result = {}

    for files in file_sets:
        for codename, file_ in files.iteritems():
            result[codename] = file_

    return result


def couple_files_to_schemas(files, schemas, operation):
    diff = set(files.iterkeys()).difference(schemas.iterkeys())
    if diff:
        logger.warning("Files codenamed %s didn't get matched to any schema "
                       "when preparing %s.", ",".join("%r" % i for i in diff),
                       operation)

    result = {}

    for codename, schema in schemas.iteritems():
        if codename in files:
            result[codename] = File(schema.filename, files[codename].digest)
        elif not schema.optional:
            logger.error("Could not find file codenamed %r when preparing %s.",
                         codename, operation)
            raise ValueError("Codename %r not provided." % codename)

    return result


def get_format_for_compilation(dataset, language, operation):
    task_type = get_task_type(dataset=dataset)

    # Obtain the schemas for each type of file.
    user_file_schemas = override_schemas(
        filter_schemas_by_language(task_type.user_file_schemas,
                                   language, operation),
        filter_schemas_by_language(dataset.user_file_schemas,
                                   language, operation),
        operation)
    dataset_file_schemas = override_schemas(
        filter_schemas_by_language(task_type.dataset_file_schemas,
                                   language, operation),
        filter_schemas_by_language(dataset.dataset_file_schemas,
                                   language, operation),
        operation)
    compilation_file_schemas = override_schemas(
        filter_schemas_by_language(task_type.compilation_file_schemas,
                                   language, operation),
        filter_schemas_by_language(dataset.compilation_file_schemas,
                                   language, operation),
        operation)

    # Merge them to obtain the global schemas.
    # The order is not important.
    merged_schemas = merge_schemas_sets(
        [user_file_schemas, dataset_file_schemas],
        operation)

    diff = set(merged_schemas.iterkeys()).intersection(
        compilation_file_schemas.iterkeys())
    if diff:
        logger.error("Schemas codenamed %s conflicted when preparing "
                     "%s.", ",".join("%r" % i for i in diff), operation)
        raise ValueError("Codenames %s conflicts." %
                         ",".join("%r" % i for i in diff))

    return merged_schemas, compilation_file_schemas


def get_files_for_compilation(schemas, submission, dataset, operation):
    language = submission.language

    # Obtain the actual files for each type of file.
    user_files = match_user_files_to_codenames(
        map_filenames_to_codenames(schemas, operation),
        submission.user_files, operation)
    dataset_files = filter_files_by_language(
        dataset.dataset_files, language, operation)

    # Merge them to obtain the global actual files.
    # The order is important! (later sets overwrite earlier ones)
    files = merge_file_sets(
        [dataset_files, user_files],
        operation)

    # Validate and add filenames.
    return couple_files_to_schemas(files, schemas, operation)


def get_format_for_evaluation(dataset, language, operation):
    task_type = get_task_type(dataset=dataset)

    # Obtain the schemas for each type of file.
    user_file_schemas = override_schemas(
        filter_schemas_by_language(task_type.user_file_schemas,
                                   language, operation),
        filter_schemas_by_language(dataset.user_file_schemas,
                                   language, operation),
        operation)
    dataset_file_schemas = override_schemas(
        filter_schemas_by_language(task_type.dataset_file_schemas,
                                   language, operation),
        filter_schemas_by_language(dataset.dataset_file_schemas,
                                   language, operation),
        operation)
    compilation_file_schemas = override_schemas(
        filter_schemas_by_language(task_type.compilation_file_schemas,
                                   language, operation),
        filter_schemas_by_language(dataset.compilation_file_schemas,
                                   language, operation),
        operation)
    testcase_file_schemas = override_schemas(
        filter_schemas_by_language(task_type.testcase_file_schemas,
                                   language, operation),
        filter_schemas_by_language(dataset.testcase_file_schemas,
                                   language, operation),
        operation)
    execution_file_schemas = override_schemas(
        filter_schemas_by_language(task_type.execution_file_schemas,
                                   language, operation),
        filter_schemas_by_language(dataset.execution_file_schemas,
                                   language, operation),
        operation)

    # Merge them to obtain the global schemas.
    # The order is not important.
    merged_schemas = merge_schemas_sets(
        [user_file_schemas, dataset_file_schemas,
         compilation_file_schemas, testcase_file_schemas],
        operation)

    diff = set(merged_schemas.iterkeys()).intersection(
        execution_file_schemas.iterkeys())
    if diff:
        logger.error("Schemas codenamed %s conflicted when preparing "
                     "%s.", ",".join("%r" % i for i in diff), operation)
        raise ValueError("Codenames %s conflicts." %
                         ",".join("%r" % i for i in diff))

    return merged_schemas, execution_file_schemas


def get_files_for_evaluation(schemas, submission, dataset,
                             submission_result, testcase, operation):
    language = submission.language

    # Obtain the actual files for each type of file.
    user_files = match_user_files_to_codenames(
        map_filenames_to_codenames(schemas, operation),
        submission.user_files, operation)
    dataset_files = filter_files_by_language(
        dataset.dataset_files, language, operation)
    compilation_files = submission_result.compilation_files
    testcase_files = filter_files_by_language(
        testcase.testcase_files, language, operation)

    # Merge them to obtain the global actual files.
    # The order is important! (later sets overwrite earlier ones)
    files = merge_file_sets(
        [dataset_files, compilation_files, testcase_files, user_files],
        operation)

    # Validate and add filenames.
    return couple_files_to_schemas(files, schemas, operation)
