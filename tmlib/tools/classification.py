# TmLibrary - TissueMAPS library for distibuted image analysis routines.
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
import logging

import tmlib.models as tm
from tmlib.utils import same_docstring_as

from tmlib.tools.base import Tool, Classifier
from tmlib.tools import register_tool

logger = logging.getLogger(__name__)


@register_tool('classification')
class Classification(Classifier):

    '''Tool for supervised classification.'''

    __icon__ = 'SVC'

    __description__ = '''
        Classifies mapobjects based on the values of selected features and
        labels provided by the user.
    '''

    __methods__ = ['svm', 'rf']

    @same_docstring_as(Tool.__init__)
    def __init__(self, experiment_id):
        super(Classification, self).__init__(experiment_id)

    def label_feature_data(self, feature_data, labeled_mapobjects):
        '''Adds labels to `feature_data` for supervised classification.

        Parameters
        ----------
        feature_data: pyspark.sql.DataFrame or pandas.DataFrame
            data frame where columns are features and rows are mapobjects
            as generated by
            :meth:`tmlib.tools.base.Classfier.format_feature_data`
        labeled_mapobjects: Tuple[int]
            ID and assigned label for each selected
            :class:`tmlib.models.mapobject.Mapobject`

        Returns
        -------
        pyspark.sql.DataFrame or pandas.DataFrame
            subset of `feature_data` for selected mapobjects with additional
            "label" column
        '''
        if self.use_spark:
            return self._label_feature_data_spark(
                feature_data, labeled_mapobjects
            )
        else:
            return self._label_feature_data_sklearn(
                feature_data, labeled_mapobjects
            )

    def _label_feature_data_spark(self, feature_data, labeled_mapobjects):
        labels = spark.sqlc.createDataFrame(
            labeled_mapobjects, schema=['mapobject_id', 'label']
        )
        labeled_data = feature_data.join(
            labels, labels['mapobject_id'] == feature_data['mapobject_id']
        ).cache()
        return labeled_data

    def _label_feature_data_sklearn(self, feature_data, labeled_mapobjects):
        labeled_mapobjects = dict(labeled_mapobjects)
        ids = labeled_mapobjects.keys()
        labels = labeled_mapobjects.values()
        labeled_feature_data = feature_data[feature_data.index.isin(ids)].copy()
        labeled_feature_data['label'] = labels
        return labeled_feature_data

    def classify(self, unlabeled_feature_data, labeled_feature_data, method):
        '''Trains a classifier for labeled mapobjects based on
        `labeled_feature_data` and predicts labels for all mapobjects in
        `unlabeled_feature_data`.

        Parameters
        ----------
        unlabeled_feature_data: pyspark.sql.DataFrame or pandas.DataFrame
            mapobjects that should be classified
        labeled_feature_data: pyspark.sql.DataFrame or pandas.DataFrame
            data that should be used for training of the classifier
        method: str
            method to use for classification

        Returns
        -------
        List[Tuple[int, str]]
            ID and predicted label for each mapobject
        '''
        if self.use_spark:
            return self._classify_spark(
                unlabeled_feature_data, labeled_feature_data, method
            )
        else:
            return self._classify_sklearn(
                unlabeled_feature_data, labeled_feature_data, method
            )

    def _classify_sklearn(self, unlabeled_feature_data, labeled_feature_data,
            method):
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.grid_search import GridSearchCV
        from sklearn import cross_validation, svm

        logger.info(
            'perform classification via Scikit-Learn with "%s" method', method
        )
        models = {
            'svm': svm.SVC,
            'rf': RandomForestClassifier
        }
        grid_search_space = {
            'svm': {
                'kernel': ['linear'],
                'C': np.linspace(0.1, 1, 5)
            },
            'rf': {
                'max_depth': [3, 5, 7],
                'min_samples_split': [1, 3, 10],
                'min_samples_leaf': [1, 3, 10]
            }
        }
        n_samples = labeled_feature_data.shape[0]
        n_folds = min(n_samples / 2, 10)

        X = labeled_feature_data.drop('label', axis=1)
        y = labeled_feature_data.label
        clf = models[method]()
        folds = cross_validation.StratifiedKFold(y, n_folds=n_folds)
        gs = GridSearchCV(clf, grid_search_space[method], cv=folds)
        logger.info('fit model')
        gs.fit(X, y)
        logger.info('collect predicted labels')
        predictions = gs.predict(unlabeled_feature_data)
        return zip(unlabeled_feature_data.index.tolist(), predictions.tolist())

    def _svm_spark(self, unlabeled_feature_data, label_df):
        from pyspark.mllib.classification import SVMWithSGD
        # TODO: grid search and crossvalidation
        label_rdd = label_df.\
            select('indexedLabel', 'features').\
            map(lambda row:
                    LabeledPoint(row.indexedLabel, row.features)
            )
        svm = SVMWithSGD.train(label_rdd, intercept=True)
        predictions = unlabeled_feature_data.\
            select('mapobject_id', 'features').\
            map(lambda row:
                    (row.mapobject_id, label_mapping[svm.predict(row.features)])
            )
        return predictions.collect()

    def _classify_spark(self, unlabeled_feature_data, labeled_feature_data,
            method):
        from pyspark.ml import Pipeline
        from pyspark.ml.feature import StringIndexer
        from pyspark.ml.feature import VectorAssembler
        from pyspark.ml.feature import VectorIndexer
        from pyspark.ml.feature import VectorAssembler, VectorIndexer, StringIndexer
        from pyspark.ml.tuning import CrossValidator, ParamGridBuilder
        from pyspark.ml.classification import RandomForestClassifier
        from pyspark.ml.evaluation import MulticlassClassificationEvaluator

        logger.info('perform classification via Spark with "%s" method', method)
        feature_indexer = VectorIndexer(
                inputCol='features', outputCol='indexedFeatures',
                maxCategories=2
            ).\
            fit(labeled_feature_data)

        label_indexer = StringIndexer(
                inputCol='label', outputCol='indexedLabel'
            ).\
            fit(labeled_feature_data)

        label_df = label_indexer.transform(labeled_feature_data)
        label_mapping = {
            r.indexedLabel: r.label
            for r in label_df.select('label','indexedLabel').distinct().collect()
        }
        # TODO: How can this be achieved with IndexToString() when prediction
        # is done on unlabeled dataset?
        # label_converter = IndexToString(
        #     inputCol='prediction', outputCol='predictedLabel',
        #     labels=label_indexer.labels
        # )

        if method == 'svm':
            # SVM is not yet implemented in the Spark DataFrame interface, but
            # in the old RDD interface. Therefore, we have to implemnt this
            # method separately.
            return self._svm_spark(unlabeled_feature_data, label_df)
        else:
            models = {
                'rf': RandomForestClassifier
            }
            grid_search_space = {
                'rf': {
                    'maxDepth': [3, 5, 7],
                    'numTrees': [10, 20, 30]
                }
            }

            clf = models[method](
                labelCol='indexedLabel', featuresCol='indexedFeatures'
            )
            grid = ParamGridBuilder()
            for k, v in grid_search_space.iteritems():
                grid.addGrid(getattr(clf, k), v)
            grid.build()

            pipeline = Pipeline(stages=[feature_indexer, label_indexer, clf])
            evaluator = MulticlassClassificationEvaluator(
                labelCol='indexedLabel', predictionCol='prediction',
                metricName='f1'
            )
            crossval = CrossValidator(
                estimator=pipeline, estimatorParamMaps=grid,
                evaluator=evaluator, numFolds=3
            )
            logger.info('fit model')
            model = crossval.fit(labeled_feature_data)
            predictions = model.transform(unlabeled_feature_data)
            logger.info('collect predicted labels')
            result = predictions.select('mapobject_id', 'prediction').collect()
            return [
                (r.mapobject_id, label_mapping[r.prediction]) for r in result
            ]

    def process_request(self, payload):
        '''Processes a client tool request and inserts the generated results
        into the database.
        The `payload` is expected to have the following form::

            {
                "choosen_object_type": str,
                "selected_features": [str, ...],
                "method": str,
                "training_classes": [
                    {
                        "name": str,
                        "object_ids": [int, ...],
                        "color": str
                    },
                    ...
                ]
            }


        Parameters
        ----------
        payload: dict
            description of the tool job
        '''
        # Get mapobject
        mapobject_type_name = payload['chosen_object_type']
        feature_names = payload['selected_features']
        method = payload['method']

        if method not in self.__methods__:
            raise ValueError('Unknown method "%s".' % method)

        labeled_mapobjects = list()
        color_map = dict()
        for cls in payload['training_classes']:
            labels = [(i, cls['name']) for i in cls['object_ids']]
            labeled_mapobjects.extend(labels)
            color_map[cls['name']] = cls['color']

        unlabeled_feature_data = self.format_feature_data(
            mapobject_type_name, feature_names
        )
        labeled_feature_data = self.label_feature_data(
            unlabeled_feature_data, labeled_mapobjects
        )
        predicted_labels = self.classify(
            unlabeled_feature_data, labeled_feature_data, method
        )

        with tm.utils.ExperimentSession(self.experiment_id) as session:
            mapobject_type_id = session.query(tm.MapobjectType.id).\
                filter_by(name=mapobject_type_name).\
                one()

            result = tm.ToolResult(self.submission_id, self.__class__.__name__)
            session.add(result)
            session.flush()

            unique_labels = np.unique(np.array(predicted_labels)[:, 1]).tolist()
            layer = tm.SupervisedClassifierLabelLayer(
                result.id, mapobject_type.id, unique_labels, color_map
            )
            session.add(layer)
            session.flush()

            label_objs = [
                {
                    'label': value,
                    'mapobject_id': mapobject_id,
                    'label_layer_id': layer.id
                }
                for mapobject_id, value in predicted_labels
            ]
            session.bulk_insert_mappings(tm.LabelLayerValue, label_objs) 
