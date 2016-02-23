interface MapState {
    zoom: number;
    center: ol.Coordinate;
    resolution: number;
    rotation: number;
}

interface SerializedViewport extends Serialized<Viewport> {
    // TODO: Create separate interface for serialized layer options.
    // The color object on channelLayerOptions isn't a full Color object
    // when restored.
    channelLayerOptions: TileLayerArgs[];
    mapState: MapState;
}

interface ViewportElementScope extends ng.IScope {
    viewport: Viewport;
    // TODO: Set type to that of ViewportCtrl
    viewportCtrl: any;
    appInstance: AppInstance;
}

class Viewport implements Serializable<Viewport> {

    element: ng.IPromise<JQuery>;
    elementScope: ng.IPromise<ViewportElementScope>;
    map: ng.IPromise<ol.Map>;

    channelLayers: ChannelLayer[] = [];
    visualLayers: VisualLayer[] = [];

    private _mapDef: ng.IDeferred<ol.Map>;
    private _elementDef: ng.IDeferred<JQuery>;
    private _elementScopeDef: ng.IDeferred<ViewportElementScope>;

    private _$q: ng.IQService;
    private _$rootScope: ng.IRootScopeService;

    constructor() {
        this._$q = $injector.get<ng.IQService>('$q');
        this._$rootScope = $injector.get<ng.IRootScopeService>('$rootScope');

        this._mapDef = this._$q.defer();
        this.map = this._mapDef.promise;

        // DEBUG
        this.map.then((map) => {
            window['map'] = map;
        });

        this._elementDef = this._$q.defer();
        this.element = this._elementDef.promise;

        this._elementScopeDef = this._$q.defer();
        this.elementScope = this._elementScopeDef.promise;
    }

    addVisualLayer(visLayer: VisualLayer): ng.IPromise<VisualLayer> {
        this.visualLayers.push(visLayer);

        // Workaround: Check where this visuallayer should be added.
        // When a new outline selection is added, it shouldn't be added on top of
        // already existing marker layers.
        // TODO: This should be done through a more general mechanism.
        insertAtPos;
        if (visLayer.contentType === ContentType.mapObject) {
            var firstMarkerLayer = _(this.visualLayers).find((l) => {
                return l.contentType === ContentType.marker;
            });
            if (firstMarkerLayer !== undefined) {
                var insertAtPos = this.visualLayers.indexOf(firstMarkerLayer);
            }
        }
        return this.map.then((map) => {
            visLayer.addToMap(map, insertAtPos);
            return visLayer;
        });
    }

    removeVisualLayer(visLayer: VisualLayer) {
        var idx = this.visualLayers.indexOf(visLayer)
        if (idx !== -1) {
            this.map.then((map) => {
                visLayer.removeFromMap(map);
                this.visualLayers.splice(idx, 1);
            });
        }
    }

    addChannelLayer(channelLayer: ChannelLayer) {
        var alreadyHasLayers = this.channelLayers.length !== 0;

        // If this is the first time a layer is added, create a view and add it to the map.
        if (!alreadyHasLayers) {
            // Center the view in the iddle of the image
            // (Note the negative sign in front of half the height)
            var width = channelLayer.imageSize[0];
            var height = channelLayer.imageSize[1];
            var center = [width / 2, - height / 2];
            var extent = [0, 0, width, height];
            console.log(extent);
            var view = new ol.View({
                // We create a custom (dummy) projection that is based on pixels
                projection: new ol.proj.Projection({
                    code: 'tm',
                    units: 'pixels',
                    extent: extent
                }),
                center: center,
                zoom: 0, // 0 is zoomed out all the way
                // starting at maxResolution where maxResolution
                // is

            });

            this.map.then(function(map) {
                map.setView(view);
            });
        }

        // Add the layer as soon as the map is created (i.e. resolved after
        // viewport injection)
        this.map.then(function(map) {
            channelLayer.addToMap(map);
        });
        this.channelLayers.push(channelLayer);
    }

    /**
     * Remove a channelLayer from the map.
     * Use this method whenever a layer should be removed since it also updates
     * the app instance's internal state.
     */
    removeChannelLayer(channelLayer: ChannelLayer) {
        this.map.then(function(map) {
            channelLayer.removeFromMap(map);
        });
        var idx = this.channelLayers.indexOf(channelLayer);
        this.channelLayers.splice(idx, 1);
    }

    /**
     * Clean up method when the instance is closed (e.g. by deleting the Tab).
     */
    destroy() {
        this.elementScope.then((scope) => {
            scope.$destroy();
            this.element.then((element) => {
                // Destroy the stuff that this instance created
                element.remove();
            });
        });
    }

    show() {
        this.element.then((element) => {
            element.show();
            this.map.then((map) => {
                map.updateSize();
            });
        });
    }

    hide() {
        this.element.then((element) => {
            element.hide();
        });
    }

    goToMapObject(obj: MapObject) {
        this.map.then((map) => {
            var feat = obj.getVisual().olFeature;
            map.getView().fit(<ol.geom.SimpleGeometry> feat.getGeometry(), map.getSize(), {
                padding: [100, 100, 100, 100]
            });
        });
    }

    serialize() {
        var bpPromise = this.map.then((map) => {
            var v = map.getView();

            var mapState = {
                zoom: v.getZoom(),
                center: v.getCenter(),
                resolution: v.getResolution(),
                rotation: v.getRotation()
            };

            var channelOptsPr = this._$q.all(_(this.channelLayers).map((l) => {
                return l.serialize();
            }));
            var bundledPromises: any = {
                channels: channelOptsPr,
            };
            return this._$q.all(bundledPromises).then((res: any) => {
                return {
                    channelLayerOptions: res.channels,
                    mapState: mapState
                };
            });
        });

        return bpPromise;
    }

    private getTemplate(templateUrl): ng.IPromise<string> {
        var deferred = this._$q.defer();
        $injector.get<ng.IHttpService>('$http')({method: 'GET', url: templateUrl, cache: true})
        .then(function(result) {
            deferred.resolve(result.data);
        })
        .catch(function(error) {
            deferred.reject(error);
        });
        return deferred.promise;
    }

    injectIntoDocumentAndAttach(appInstance: AppInstance) {
        this.getTemplate('/templates/main/viewport.html').then((template) => {
            var newScope = <ViewportElementScope> this._$rootScope.$new();
            newScope.viewport = this;
            newScope.appInstance = appInstance;
            var ctrl = $injector.get<any>('$controller')('ViewportCtrl', {
                '$scope': newScope,
                'viewport': this
            });
            newScope.viewportCtrl = ctrl;

            // The divs have to be shown and hidden manually since ngShow
            // doesn't quite work correctly when doing it this way.
            var elem = angular.element(template);

            // Compile the element (expand directives)
            var linkFunc = $injector.get<ng.ICompileService>('$compile')(elem);
            // Link to scope
            var viewportElem = linkFunc(newScope);

            // Append to viewports
            $injector.get<ng.IDocumentService>('$document').find('#viewports').append(viewportElem);
            // Append map after the element has been added to the DOM.
            // Otherwise the viewport size calculation of openlayers gets
            // messed up.
            var map = new ol.Map({
                layers: [],
                controls: [],
                renderer: 'webgl',
                target: viewportElem.find('.map-container')[0],
                logo: false
            });
            this._elementDef.resolve(viewportElem);
            this._elementScopeDef.resolve(newScope);
            this._mapDef.resolve(map);
        });
    }
}
