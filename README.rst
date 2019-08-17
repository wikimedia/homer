Homer - Configuration manager for network devices
-------------------------------------------------

Homer allows to manage the lifecycle of the configuration for network devices, generating and deploying their
configuration.
The configuration generation is based on ``YAML`` files to define variables and ``Jinja2`` templates.
The ``YAML`` files allow for hierarchical override of variables based on the device role, site or hostname.
Once generated, the configuration can also be deployed to their devices.
