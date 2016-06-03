interface PlateArgs {
    id: string;
    name: string;
    description: string;
    acquisitions: Acquisition[];
}

class Plate {
    id: string;
    name: string;
    description: string;
    status: any;
    acquisitions: Acquisition[];

    /**
     * Constructor a new Plate object.
     *
     * @class Plate
     * @classdesc A plate is basically a container for multiple objects
     * of type Acquisition.
     * @param {PlateArgs} args - Constructor arguments.
     */
    constructor(args: PlateArgs) {
        this.id = args.id;
        this.name = args.name;
        this.description = args.description;
        this.acquisitions = args.acquisitions;
    }

    get isReadyForProcessing() {
        var hasMinOneAcquisition = this.acquisitions.length > 0; 
        var allAcquisitionsReady = _.all(this.acquisitions.map((aq) => {
            return aq.status === 'COMPLETE';
        }));
        return hasMinOneAcquisition && allAcquisitionsReady;
    }
}
