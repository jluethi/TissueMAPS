# encoding: utf-8
import os
import sys
import traceback
import logging
import shutil
import argparse
import gc3libs
from abc import ABCMeta
from abc import abstractproperty
from abc import abstractmethod
from . import cfg
from .logging_utils import configure_logging

logger = logging.getLogger(__name__)


def command_line_call(parser):
    '''
    Main entry point for command line interfaces.

    Parsers the command line arguments to the corresponding handler
    and configures logging.

    Parameters
    ----------
    parser: argparse.ArgumentParser
        argument parser object

    Warning
    -------
    Don't do any other logging configuration anywhere else!
    '''
    args = parser.parse_args()

    if args.verbosity > 0:
        level = logging.DEBUG
    else:
        level = logging.INFO
    if args.silent:
        level = logging.CRITICAL
    configure_logging(level)
    logger.debug('running program: %s' % parser.prog)

    gc3libs.log = logging.getLogger('gc3lib')
    gc3libs.log.level = logging.CRITICAL

    try:
        if args.handler:
            args.handler(args)
            sys.stdout.write('🍺  Done!')
        else:
            parser.print_help()
    except Exception as error:
        sys.stderr.write('😞  Failed!\n')
        sys.stderr.write(str(error))
        for tb in traceback.format_tb(sys.exc_info()[2]):
            sys.stderr.write(tb)


class CommandLineInterface(object):

    '''
    Abstract base class for command line interfaces.

    Note
    ----
    There must be a method for each subparser, where the name of the method
    has to match the name of the corresponding subparser.
    '''

    __metaclass__ = ABCMeta

    def __init__(self, args):
        '''
        Initialize an instance of class CommandLineInterface.

        Parameters
        ----------
        args: argparse.Namespace
            parsed command line arguments

        Note
        ----
        Default configuration settings are overwritten in case a custom
        configuration file is provided via the command line.
        '''
        self.args = args

    @property
    def cfg(self):
        '''
        Returns
        -------
        Dict[str, str]
            configuration settings
        '''
        self._cfg = cfg
        return self._cfg

    @abstractproperty
    def name(self):
        '''
        Returns
        -------
        str
            name of the program
        '''
        pass

    @abstractproperty
    def _api_instance(self):
        pass

    @abstractmethod
    def call(args):
        '''
        Handler function that can be called by a subparser.

        Initializes an instance of the class and calls the method matching the
        name of the specified subparser with the parsed arguments.

        Parameters
        ----------
        args: argparse.Namespace
            parsed command line arguments

        Note
        ----
        `args` must have the attribute "subparser_name", which specifies the
        name of the subparser.
        '''
        pass

    @abstractmethod
    def print_logo():
        pass

    @property
    def _variable_init_args(self):
        # Since "init" requires more flexibility with respect to the number
        # of parsed arguments, we use a separate property, which can be
        # overwritten by subclasses to handle custom use cases
        kwargs = dict()
        return kwargs

    def init(self):
        '''
        Initialize an instance of the API class corresponding to the program
        and process arguments of the "init" subparser.

        Returns
        -------
        dict
            job descriptions
        '''
        self.print_logo()
        api = self._api_instance
        job_descriptions = api.get_job_descriptions_from_files()
        if job_descriptions['run']:
            logger.info('clean up output of previous submission')
            output_files = api.list_output_files(job_descriptions)
            # TODO
            if not output_files:
                logger.debug('no output files of previous submission found')
            else:
                logger.debug('remove output files of previous submission')
                if all([not os.path.exists(f) for f in output_files]):
                    logger.warning('output files don\'t exist')
                elif any([not os.path.exists(f) for f in output_files]):
                    logger.warning('some output files don\'t exist')
                [os.remove(f) for f in output_files
                 if os.path.exists(f) and not os.path.isdir(f)]
            if self.args.backup:
                logger.info('backup project directory of previous submission')
                timestamp = api.create_datetimestamp()
                shutil.move(api.log_dir,
                            '{name}_backup_{time}'.format(
                                        name=api.log_dir,
                                        time=timestamp))
                shutil.move(api.job_descriptions_dir,
                            '{name}_backup_{time}'.format(
                                        name=api.job_descriptions_dir,
                                        time=timestamp))
            else:
                logger.debug('remove log reports and job descriptions '
                             'of previous submission')
                shutil.rmtree(api.job_descriptions_dir)
                shutil.rmtree(api.log_dir)

        logger.info('create job descriptions')
        kwargs = self._variable_init_args
        job_descriptions = api.create_job_descriptions(**kwargs)
        if self.args.print_job_descriptions:
            api.print_job_descriptions(job_descriptions)
        else:
            logger.info('write job descriptions to files')
            api.write_job_files(job_descriptions)
        return job_descriptions

    def run(self):
        '''
        Initialize an instance of the API class corresponding to the program
        and process arguments of the "run" subparser.
        '''
        self.print_logo()
        api = self._api_instance
        logger.info('read job description from file')
        job_file = api.build_run_job_filename(self.args.job)
        batch = api.read_job_file(job_file)
        logger.info('run job #%d' % batch['id'])
        api.run_job(batch)

    def get_jobs(self):
        '''
        Read the job descriptions from the *.job* files and build GCPie "jobs".

        Returns
        -------
        gc3libs.workflow.SequentialTaskCollection
            jobs
        '''
        api = self._api_instance
        logger.info('read job descriptions from files')
        job_descriptions = api.get_job_descriptions_from_files()
        logger.info('create jobs')
        jobs = api.create_jobs(
                job_descriptions=job_descriptions,
                no_shared_network=self.args.no_shared_network,
                virtualenv=self.args.virtualenv)
        return jobs

    def submit(self):
        '''
        Initialize an instance of the API class corresponding to the program
        and process arguments of the "submit" subparser.
        '''
        self.print_logo()
        api = self._api_instance
        jobs = self.get_jobs()
        logger.info('submit and monitor jobs')
        api.submit_jobs(jobs, self.args.interval)

    def kill(self):
        '''
        Initialize an instance of the API class corresponding to the program
        and process arguments of the "kill" subparser.
        '''
        self.print_logo()
        api = self._api_instance
        jobs = self.get_jobs()
        logger.info('kill jobs')
        api.kill_jobs(jobs)

    @property
    def _variable_apply_args(self):
        kwargs = dict()
        return kwargs

    def apply(self):
        '''
        Initialize an instance of the API class corresponding to the program
        and process arguments of the "apply" subparser.
        '''
        self.print_logo()
        api = self._api_instance
        logger.info('read job descriptions from files')
        job_descriptions = api.get_job_descriptions_from_files()
        logger.info('apply statistics')
        kwargs = self._variable_apply_args
        api.apply_statistics(
                job_descriptions=job_descriptions,
                wells=self.args.wells, sites=self.args.sites,
                channels=self.args.channels, output_dir=self.args.output_dir,
                **kwargs)

    def collect(self):
        '''
        Initialize an instance of the API class corresponding to the program
        and process arguments of the "collect" subparser.
        '''
        self.print_logo()
        api = self._api_instance
        logger.info('read job description from file')
        job_file = api.build_collect_job_filename()
        batch = api.read_job_file(job_file)
        logger.info('collect job output')
        api.collect_job_output(batch)

    @staticmethod
    def get_parser_and_subparsers(
            required_subparsers=['init', 'run', 'submit', 'kill']):
        '''
        Get an argument parser object and subparser objects with default
        arguments for use in command line interfaces.
        The subparsers objects can be extended with additional subparsers and
        additional arguments can be added to each individual subparser.

        Parameters
        ----------
        required_subparsers: List[str]
            subparsers that should be returned (defaults to
            ``["init", "run", "submit"]``)
        level: str
            level of the directory tree at which the command line interface
            operates; "cycle" when processing data at the level of an individual
            *cycle* folder or "experiment" when processing data at the level of
            the *experiment* folder, i.e. across multiple *cycle* folders

        Returns
        -------
        Tuple[argparse.Argumentparser and argparse._SubParsersAction]
            parser and subparsers objects
        '''
        parser = argparse.ArgumentParser()
        parser.add_argument(
            'experiment_dir', help='path to experiment directory')
        parser.add_argument(
            '-v', '--verbosity', action='count', default=0,
            help='increase logging verbosity to DEBUG (default: INFO)')
        parser.add_argument(
            '-s', '--silent', action='store_true',
            help='set logging verbosity to WARNING')
        parser.add_argument(
            '--version', action='version')

        if not required_subparsers:
            raise ValueError('At least one subparser has to specified')

        subparsers = parser.add_subparsers(dest='subparser_name',
                                           help='sub-commands')

        if 'init' in required_subparsers:
            init_parser = subparsers.add_parser(
                'init', help='initialize the program with required arguments')
            init_parser.description = '''
                Create a list of job descriptions (batches) for parallel
                processing and write it to a file in JSON format. Note that in
                case of existing previous submissions, the log output will be
                overwritten unless either the "--backup" or "--show" argument
                is specified.
            '''
            init_parser.add_argument(
                '--show', action='store_true', dest='print_job_descriptions',
                help='print joblist to standard output '
                     'without writing it to file')
            init_parser.add_argument(
                '--backup', action='store_true',
                help='create a backup of the output of a previous submission')
            # NOTE: when additional arguments are provided, the property
            # `_variable_init_args` has to be overwritten

        if 'run' in required_subparsers:
            run_parser = subparsers.add_parser(
                'run',
                help='run an individual job')
            run_parser.description = '''
                Run an individual job.
            '''
            run_parser.add_argument(
                '-j', '--job', type=int, required=True,
                help='id of the job that should be processed')

        if 'submit' in required_subparsers:
            submit_parser = subparsers.add_parser(
                'submit',
                help='submit and monitor jobs')
            submit_parser.description = '''
                Create jobs, submit them to the cluster, monitor their
                processing and collect their outputs.
            '''
            submit_parser.add_argument(
                '--interval', type=int, default=5,
                help='monitoring interval in seconds'
            )
            submit_parser.add_argument(
                '--no_shared_network', dest='no_shared_network',
                action='store_true', help='when worker nodes don\'t have \
                access to a shared network; triggers copying of files')
            submit_parser.add_argument(
                '--virtualenv', type=str, default='tmaps',
                help='name of a virtual environment that should be activated '
                     '(default: tmaps')

        if 'kill' in required_subparsers:
            kill_parser = subparsers.add_parser(
                'kill',
                help='kill submitted jobs')
            kill_parser.description = '''
                Stop submitted jobs and set their status to "terminated".
            '''
            kill_parser.add_argument(
                '--no_shared_network', dest='no_shared_network',
                action='store_true', help='when worker nodes don\'t have \
                access to a shared network; triggers copying of files')
            kill_parser.add_argument(
                '--virtualenv', type=str, default='tmaps',
                help='name of a virtual environment that should be activated '
                     '(default: tmaps')

        if 'collect' in required_subparsers:
            collect_parser = subparsers.add_parser(
                'collect',
                help='collect job output after submission')
            collect_parser.description = '''
                Collect outputs of processed jobs and fuse them.
            '''
            collect_parser.add_argument(
                '-o', '--output_dir', type=str,
                help='path to output directory')

        if 'apply' in required_subparsers:
            apply_parser = subparsers.add_parser(
                'apply',
                help='apply the calculated statistics')
            apply_parser.description = '''
                Apply the calculated statistics.
            '''
            apply_parser.add_argument(
                '-c', '--channels', nargs='+', type=str,
                help='names of channels to process')
            apply_parser.add_argument(
                '-s', '--sites',  nargs='+', type=int,
                help='numbers of sites to process')
            apply_parser.add_argument(
                '-w', '--wells', nargs='+', type=str,
                help='ids of wells to process')
            apply_parser.add_argument(
                '-a', '--all', action='store_true',
                help='when all images should be processed')
            apply_parser.add_argument(
                '-o', '--output_dir', type=str, required=True,
                help='path to output directory')

        return (parser, subparsers)
