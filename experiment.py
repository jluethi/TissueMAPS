import re
import os
from os.path import isdir, join, basename, dirname, exists
from natsort import natsorted
from image_toolbox.util import regex_from_format_string
from image_toolbox.project import Project


class Experiment(object):
    '''Utility class for an experiment.
    An experiment may represent a "project" itself or it may contain one or
    several subexperiments, each of them representing a "project".   
    '''

    def __init__(self, experiment_dir, cfg):
        '''
        Initialize Experiment class.
        An Experiment may hold subexperiments.

        Parameters:
        :experiment_dir:    Absolute path to experiment folder. : str
        :cfg:               Configuration settings. : dict
        '''
        self.cfg = cfg
        self.experiment_dir = experiment_dir
        self.experiment_name = basename(experiment_dir)
        self._subexperiments = None
        self._project = None

    def is_valid_subexperiment(self, folder_name):
        regexp = regex_from_format_string(
                        self.cfg['SUBEXPERIMENT_FOLDER_FORMAT'])
        return(re.match(regexp, folder_name)
               and isdir(join(self.experiment_dir, folder_name)))

    @property
    def subexperiments(self):
        if not self._subexperiments:
            experiment_subfolders = os.listdir(self.experiment_dir)
            experiment_subfolders = natsorted(experiment_subfolders)
            folders = [Subexperiment(join(self.experiment_dir, f), self.cfg)
                       for f in experiment_subfolders
                       if self.is_valid_subexperiment(f)]
            if not folders:
                raise Exception('Experiment "%s" does not contain any '
                                'subexperiments' % self.experiment_name)
            self._subexperiments = folders
        return self._subexperiments

    @property
    def project(self):
        if self._project is None:
            self._project = Project(self.experiment_dir, self.cfg)
        return self._project
    

class Subexperiment(object):
    '''Utility class for a subexperiment.
    A subexperiment represents a child folder of an experiment folder.
    The class provides information on the subexperiment, such as its name,
    cycle number, and parent experiment's name.
    '''

    def __init__(self, subexperiment_dir, cfg):
        '''
        Initialize Subexperiment class.

        Parameters:
        :subexperiment_dir: Path to the subexperiment folder : str.
        :cfg:               Configuration settings : dict.
        '''
        self.directory = subexperiment_dir
        self.name = basename(subexperiment_dir)
        self.cfg = cfg
        self._experiment = None
        self._cycle = None
        self._project = None

    @property
    def experiment(self):
        if self._experiment is None:
            regexp = regex_from_format_string(
                            self.cfg['SUBEXPERIMENT_FOLDER_FORMAT'])
            m = re.search(regexp, self.name)
            if not m:
                raise Exception('Can\'t determine experiment name from '
                                'subexperiment folder "%s"' % self.name)
            self._experiment = m.group('experiment')
        return self._experiment

    @property
    def cycle(self):
        if self._cycle is None:
            regexp = regex_from_format_string(
                            self.cfg['SUBEXPERIMENT_FOLDER_FORMAT'])
            m = re.search(regexp, self.name)
            if not m:
                raise Exception('Can\'t determine cycle number from '
                                'subexperiment folder "%s"' % self.name)
            self._cycle = int(m.group('cycle'))
        return self._cycle

    @property
    def project(self):
        if self._project is None:
            self._project = Project(dirname(self.directory), self.cfg,
                                    subexperiment=self.name)
        return self._project
    

    def __str__(self):
        return '%s - %s' % (self.experiment, self.cycle)

    def __unicode__(self):
        return self.__str__()
