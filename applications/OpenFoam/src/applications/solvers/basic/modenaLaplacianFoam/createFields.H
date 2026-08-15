    Info<< "Reading field T\n" << endl;

    volScalarField T
    (
        IOobject
        (
            "T",
            runTime.timeName(),
            mesh,
            IOobject::MUST_READ,
            IOobject::AUTO_WRITE
        ),
        mesh
    );

    Info<< "Reading transportProperties\n" << endl;

    std::unique_ptr<modena::Model> modelPtr;
    std::size_t Tpos  = 0;
    std::size_t DTpos = 0;

    if (MODENA_RUN)
    {
        try
        {
            modelPtr.reset(new modena::Model("thermalDiffusion"));
            Tpos  = modelPtr->input_pos("T");
            DTpos = modelPtr->output_pos("DT");
            modelPtr->check();
        }
        catch (const modena::Exception& e)
        {
            return e.code;
        }
    }

    IOdictionary transportProperties
    (
        IOobject
        (
            "transportProperties",
            runTime.constant(),
            mesh,
            IOobject::MUST_READ_IF_MODIFIED,
            IOobject::NO_WRITE
        )
    );

    volScalarField DT
    (
        IOobject
        (
            "DT",
            runTime.timeName(),
            mesh,
            IOobject::NO_READ,
            IOobject::AUTO_WRITE
        ),
        mesh,
        dimensionedScalar(transportProperties.lookup("DT"))
    );
