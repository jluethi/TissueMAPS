# TmServer - TissueMAPS server application.
# Copyright (C) 2016  Markus D. Herrmann, University of Zurich and Robin Hafen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Jterator user interface view functions."""
import os
import time
import json
import re
import glob
import yaml
import logging
import base64
import subprocess
from werkzeug import secure_filename
from natsort import natsorted
from flask import send_file, jsonify, request
from flask_jwt import jwt_required
from flask_jwt import current_identity

import tmlib.models as tm
from tmlib import cfg as libcfg
from tmlib.utils import flatten
from tmlib.workflow import get_step_args
from tmlib.workflow.jobs import RunJob
from tmlib.workflow.jobs import RunPhase
import tmlib.workflow.utils as cluster_utils
from tmlib.log import configure_logging
from tmlib.workflow.jterator.api import ImageAnalysisPipelineEngine
from tmlib.workflow.jterator.project import Project, AvailableModules
from tmlib.workflow.jterator.description import (
    PipelineDescription, HandleDescriptions
)

from tmserver.util import decode_query_ids
from tmserver.util import assert_form_params, assert_query_params
from tmserver.extensions import gc3pie
from tmserver.jtui import jtui
# from tmserver.jtui import register_error
from tmserver.error import (
    MalformedRequestError,
    MissingGETParameterError,
    MissingPOSTParameterError,
    ResourceNotFoundError,
    NotAuthorizedError,
    HTTPException
)


logger = logging.getLogger(__name__)


def list_module_names(pipeline):
    '''Lists all names of active module in the pipeline.

    Parameters
    ----------
    pipeline: dict
        pipeline description

    Returns
    -------
    List[str]
        module names
    '''
    modules_names = [
        os.path.splitext(
            os.path.splitext(
                os.path.basename(m.handles)
            )[0]
        )[0]
        for m in pipeline if m.active
    ]
    return modules_names


@jtui.route('/experiments/<experiment_id>/project', methods=['GET'])
@jwt_required()
@decode_query_ids()
def get_project(experiment_id):
    '''Gets the Jterator
    :class:`Project <tmlib.workflow.jterator.project.Project>`
    for a given experiment.
    It consists of a pipeline description ("pipe") and
    several module descriptions ("handles").
    '''
    logger.info('get jterator project for experiment %d', experiment_id)
    jt = ImageAnalysisPipelineEngine(experiment_id)
    serialized_project = yaml.safe_dump(jt.project.to_dict())
    return jsonify(jtproject=serialized_project)


@jtui.route('/experiments/<experiment_id>/project', methods=['POST'])
@jwt_required()
@assert_form_params('project')
@decode_query_ids()
def update_project(experiment_id):
    '''Saves modifications of the pipeline and module descriptions to the
    corresponding `.pipe` and `.handles` files.
    '''
    logger.info('save jterator project of experiment %d', experiment_id)
    data = json.loads(request.data)
    project = yaml.load(data['project'])
    pipeline_description = PipelineDescription(**project['pipe']['description'])
    handles_descriptions = {
        h['name']: HandleDescriptions(**h['description'])
        for h in project['handles']
    }
    jt = ImageAnalysisPipelineEngine(
        experiment_id,
        pipeline_description=pipeline_description,
        handles_descriptions=handles_descriptions,
    )
    try:
        jt.project.save()
        return jsonify({'success': True})
    except Exception as err:
        raise MalformedRequestError('Project could not be saved:\n%s', str(err))


@jtui.route('/available_modules')
@jwt_required()
def get_available_modules():
    '''Lists all available Jterator modules in the
    `JtLibrary <https://github.com/TissueMAPS/JtLibrary>`_ repository.
    '''
    logger.info('get list of available jterator modules')
    repo_location = libcfg.modules_home
    modules = AvailableModules(repo_location)
    return jsonify(jtmodules=modules.to_dict())


@jtui.route('/available_pipelines')
@jwt_required()
def get_available_pipelines():
    '''Lists all available Jterator pipelines in the
    `JtLibrary <https://github.com/TissueMAPS/JtLibrary>`_ repository.
    '''
    logger.info('get list of available jterator pipelines')
    pipes_location = os.path.join(libcfg.modules_home, 'pipes')
    pipes = [
        os.path.basename(p)
        for p in list_projects(pipes_location)
    ]
    pipes = []
    return jsonify(jtpipelines=pipes)


@jtui.route('/experiments/<experiment_id>/available_channels')
@jwt_required()
@decode_query_ids()
def get_available_channels(experiment_id):
    '''Lists all channels for a given experiment.'''
    logger.info(
        'get list of available channels for experiment %d', experiment_id
    )
    with tm.utils.ExperimentSession(experiment_id) as session:
        channels = session.query(tm.Channel)
        return jsonify(channels=[c.name for c in channels])


@jtui.route('/module_source_code')
@assert_query_params('module_filename')
@jwt_required()
def get_module_source_code():
    '''Gets the source code for a given module.'''
    module_filename = request.args.get('module_filename')
    logger.info('get source code of module file "%s"', module_filename)
    modules = AvailableModules(libcfg.modules_home)
    files = [
        f for i, f in enumerate(modules.module_files)
        if os.path.basename(f) == module_filename
    ]
    return send_file(files[0])


@jtui.route('/experiments/<experiment_id>/figure')
@jwt_required()
@assert_query_params('module_name', 'job_id')
@decode_query_ids()
def get_module_figure(experiment_id):
    '''Gets the figure for a given module.'''
    module_name = request.args.get('module_name')
    job_id = request.args.get('job_id', type=int)
    logger.info(
        'get figure for module "%s" and job %d of experiment %d',
        module_name, job_id, experiment_id
    )
    jt = ImageAnalysisPipelineEngine(experiment_id)
    fig_file = [
        m.build_figure_filename(jt.figures_location, job_id)
        for m in jt.pipeline if m.name == module_name
    ]
    if len(fig_file) == 0:
        return jsonify({
            'success': False,
            'error': 'No figure file found for module "%s"' % module_name
        })
    fig_file = fig_file[0]
    if os.path.exists(fig_file):
        return send_file(fig_file)
    else:
        return jsonify({
            'success': False,
            'error': 'No figure file found for module "%s"' % module_name
        })


@jtui.route('/experiments/<experiment_id>/joblist', methods=['POST'])
@jwt_required()
@decode_query_ids()
def create_joblist(experiment_id):
    '''Creates a list of jobs for the current project to give the user a
    possiblity to select a site of interest.
    '''
    logger.info(
        'create list of jterator jobs of experiment %d', experiment_id
    )
    metadata = dict()
    with tm.utils.ExperimentSession(experiment_id) as session:
        query = session.query(
                tm.Site.y, tm.Site.x,
                tm.Well.name.label('well'),
                tm.Plate.name.label('plate')
            ).\
            join(tm.Well).\
            join(tm.Plate).\
            order_by(tm.Site.id)
        for index, record in enumerate(query):
            metadata[index+1] = {
                'plate': record.plate,
                'well': record.well,
                'y': record.y,
                'x': record.x,
            }
    return jsonify({'joblist': metadata})


@jtui.route('/experiments/<experiment_id>/project/check', methods=['POST'])
@jwt_required()
@assert_form_params('project')
@decode_query_ids()
def check_project(experiment_id):
    '''Checks pipeline and module descriptions.
    '''
    logger.info(
        'check description of jterator project of experiment %d', experiment_id
    )
    data = json.loads(request.data)
    project = yaml.load(data['project'])
    pipeline_description = PipelineDescription(**project['pipe']['description'])
    handles_descriptions = {
        h['name']: HandleDescriptions(**h['description'])
        for h in project['handles']
    }
    try:
        jt = ImageAnalysisPipelineEngine(
            experiment_id,
            pipeline_description=pipeline_description,
            handles_descriptions=handles_descriptions,
        )
        return jsonify(success=True)
    except Exception as err:
        raise MalformedRequestError('Pipeline check failed:\n%s' % str(err))


@jtui.route('/experiments/<experiment_id>/project', methods=['DELETE'])
@jwt_required()
@decode_query_ids()
def delete_project(experiment_id):
    '''Removes `.pipe` and `.handles` files from a given Jterator project.
    '''
    logger.info('delete jterator project of experiment %d', experiment_id)
    jt = ImageAnalysisPipelineEngine(experiment_id, )
    jt.project.remove()
    return jsonify({'success': True})


@jtui.route('/experiments/<experiment_id>/jobs/kill', methods=['POST'])
@assert_form_params('task_id')
@jwt_required()
@decode_query_ids()
def kill_jobs(experiment_id):
    '''Kills submitted jobs.'''
    # TODO
    task = gc3pie.retrieve_task(task_id)
    gc3pie.kill_task(task)


def _get_output(jobs, modules, fig_location):
    output = list()
    if jobs is None:
        return output
    for task in jobs.iter_workflow():
        if not isinstance(task, RunPhase):
            continue
        for subtask in task.iter_tasks():
            if not isinstance(subtask, RunJob):
                continue
            j = int(re.search(r'_(\d+)$', subtask.jobname).group(1))
            stdout_file = os.path.join(subtask.output_dir, subtask.stdout)
            if os.path.exists(stdout_file):
                with open(stdout_file) as f:
                    stdout = f.read()
            else:
                stdout = ''
            stderr_file = os.path.join(subtask.output_dir, subtask.stderr)
            if os.path.exists(stderr_file):
                with open(stderr_file) as f:
                    stderr = f.read()
            else:
                stderr = ''

            with tm.utils.MainSession() as session:
                task_info = session.query(tm.Task).get(subtask.persistent_id)
                exitcode = task_info.exitcode
                submission_id = task_info.submission_id
            failed = exitcode != 0
            output.append({
                'id': j,
                'submission_id': submission_id,
                'name': subtask.jobname,
                'stdout': stdout,
                'stderr': stderr,
                'failed': failed
            })
    return output


@jtui.route('/experiments/<experiment_id>/jobs/status', methods=['POST'])
@jwt_required()
@decode_query_ids()
def get_job_status(experiment_id):
    '''Gets the status of submitted jobs.'''
    job_collection_id = gc3pie.get_id_of_most_recent_task(experiment_id, 'jtui')
    if job_collection_id is None:
        status = {}
    else:
        status = gc3pie.get_task_status(job_collection_id)
    return jsonify(status=status)


@jtui.route('/experiments/<experiment_id>/jobs/output', methods=['POST'])
@jwt_required()
@assert_form_params('project')
@decode_query_ids()
def get_job_output(experiment_id):
    '''Gets output generated by a previous submission.'''
    data = json.loads(request.data)
    project = yaml.load(data['project'])
    pipeline_description = PipelineDescription(**project['pipe']['description'])
    handles_descriptions = {
        h['name']: HandleDescriptions(**h['description'])
        for h in project['handles']
    }
    jt = ImageAnalysisPipelineEngine(
        experiment_id,
        pipeline_description=pipeline_description,
        handles_descriptions=handles_descriptions,
    )
    try:
        jobs = gc3pie.retrieve_most_recent_task(experiment_id, 'jtui')
        output = _get_output(jobs, jt.pipeline, jt.figures_location)
        return jsonify(output=output)
    except IndexError:
        return jsonify(output=None)


@jtui.route('/experiments/<experiment_id>/jobs/run', methods=['POST'])
@jwt_required()
@assert_form_params('job_ids', 'project')
@decode_query_ids()
def run_jobs(experiment_id):
    '''Runs one or more jobs of the current project with pipeline and module
    descriptions provided by the UI.

    This requires the pipeline and module descriptions to be saved to *pipe*
    and *handles* files, respectively.
    '''
    logger.info(
        'submit jobs for jterator project of experiment %d', experiment_id
    )
    data = json.loads(request.data)
    job_ids = map(int, data['job_ids'])
    project = yaml.load(data['project'])
    pipeline_description = PipelineDescription(**project['pipe']['description'])
    handles_descriptions = {
        h['name']: HandleDescriptions(**h['description'])
        for h in project['handles']
    }
    jt = ImageAnalysisPipelineEngine(
        experiment_id,
        pipeline_description=pipeline_description,
        handles_descriptions=handles_descriptions,
    )

    # 1. Delete figures and logs from previous submission
    #    since they are not tracked per submission.
    jt.remove_previous_pipeline_output()
    # TODO: remove figure files of previous runs!!

    # 2. Build job descriptions
    channel_names = [
        ch.name for ch in jt.project.pipe.description.input.channels
    ]
    job_descriptions = list()
    with tm.utils.ExperimentSession(experiment_id) as session:
        for j in job_ids:
            image_file_count = session.query(tm.ChannelImageFile.id).\
                join(tm.Channel).\
                filter(tm.Channel.name.in_(channel_names)).\
                filter(tm.ChannelImageFile.site_id == j).\
                count()
            if image_file_count == 0:
                raise MalformedRequestError('No images found for job ID %s.' % j)
            job_descriptions.append({'site_id': j, 'plot': True})

    with tm.utils.MainSession() as session:
        submission = tm.Submission(
            experiment_id=experiment_id, program='jtui',
            user_id=current_identity.id
        )
        session.add(submission)
        session.flush()

        SubmitArgs = get_step_args('jterator')[1]
        submit_args = SubmitArgs()
        job_collection = jt.create_debug_run_phase(submission.id)
        jobs = jt.create_debug_run_jobs(
            user_name=current_identity.name,
            batches=job_descriptions,
            job_collection=job_collection,
            verbosity=2,
            duration=submit_args.duration,
            memory=submit_args.memory,
            cores=submit_args.cores
        )

    # 3. Store jobs in session
    gc3pie.store_task(jobs)
    # session.remove(data['previousSubmissionId'])
    gc3pie.submit_task(jobs)
    return jsonify(submission_id=jobs.submission_id)
