Homer - Configuration manager for network devices
-------------------------------------------------

Homer allows to manage the lifecycle of the configuration for network devices, generating and deploying their
configuration.

The configuration generation is based on ``YAML`` files to define variables and ``Jinja2`` templates.
The ``YAML`` files allow for hierarchical override of variables based on the device role, site or hostname.
Once generated, the configuration can be deployed to the selected devices.

The device list can either live hardcoded in the configuration files or be dynamically gathered from Netbox.
When using Netbox as inventory both the Virtual Chassis endpoint and the Device endpoint are used to select
all the devices that matches the configured whitelist of device roles and statuses.

Also when using Netbox as inventory for each device additional metadata is exposed to the templates, namely:

- ``role``: device role slug
- ``site``: device site slug
- ``type``: device type slug
- ``ip4``: primary IPv4 without netmask
- ``ip6``: primary IPv6 without netmask
- ``netbox_object``: the Netbox device object. Directly exposed data should always be preferred in templates.
  It is exposed to not be a blocker in case some additional data is needed that is not yet exposed by
  Homer explicitely. It could be removed in a future release.
