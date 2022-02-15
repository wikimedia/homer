Homer Changelog
---------------

`v0.4.0`_ (2022-02-15)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* netbox: inject in the device metadata also the device status from Netbox so that it can be used to query
  (i.e. status:active).

Bug fixes
"""""""""

* transports.junos: catch another timeout exception (``jnpr.junos.exception.RpcTimeoutError``) on close that was raised
  in some real life usage.

`v0.3.0`_ (2022-01-19)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* Added option to disable Capirca ACL generation completely

Bug fixes
"""""""""

* Capirca: disable shade check
* Force paramiko to 2.8.1

Miscellanea
"""""""""""

* Bump Capirca to 2.0.4

`v0.2.9`_ (2021-11-09)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* transports: catch connection error:

  * To prevent that a connection error on one device fails the entire run for all devices, catch a new
    ``HomerConnectError`` when executing the action on the devices.
  * JunOS transport: raise ``HomerConnectError`` when failing to connect to the device.
  * Exceptions: add a new ``HomerConnectError`` exception class.
  * Fix typo in retry log message on timeout.

Miscellanea
"""""""""""

* Add Python 3.9 support.
* setup.py: include type hints for dependencies.
* pylint: fixed newly reported issues.

`v0.2.8`_ (2021-04-29)
^^^^^^^^^^^^^^^^^^^^^^

Bug fixes
"""""""""

* setup.py: limit max version of pynetbox that in release 6.0.0 introduced some breacking changes in the API.
* doc: fix documentation generation that prevented from properly including the auto-generated documentation.

`v0.2.7`_ (2021-04-20)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""
* Add Capirca support.

  * For examples on how to use it see `gerrit/663535`_ and Homer's `Capirca documentation`_ (`T273865`_).

Bug fixes
"""""""""

* tests: fix pip backtracking moving prospector to its own environment in tox.
* tests: add missing tests for the circuits and vlan capabilities in the Netbox module.
* tests: add missing tests for the device data inventory.
* tests: fix typo in mocked object.
* tests: fix deprecated pytest CLI argument.

`v0.2.6`_ (2021-01-07)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* junos: colorize configuration diff (`T260769`_).
* netbox: add device's inventory support (`T257392`_).
* netbox: add per device ``_get_vlans()``. Get all the intefaces of a device and generate a dict with all the vlans
  configured on those interfaces.

Minor improvements
""""""""""""""""""

* junos: catch exceptions in rollbacks. The rollback operation could also fail, catch the error and log it but do not
  make the whole run to fail.

Miscellanea
"""""""""""

* dependency: remove temporary upper limit for test dependency prospector, not needed anymore.
* tox: remove ``--skip B322`` from Bandit config, not supported anymore.
* type hints: mark the package as type hinted, making it PEP 561 compatible.

`v0.2.5`_ (2020-08-13)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* netbox: make Netbox errors surface through Jinja:

  * When an error in the calls to Netbox API occurs it currently gets swallowed by Jinja behing an ``UndefinedError``.
  * Make it explicitely raise an ``HomerError`` that gets correctly reported from Jinja showing the original traceback,
    needed for debug.

* templates: add support for private templates:

  * Tell Jinja2 to load templates also from the private path if it's set, to enable the support for private templates
    or subtemplates.

* netbox: add circuits support:

  * Pulls all the cables terminating on the target device to then find the circuits attached to those cables.

Miscellanea
"""""""""""
* setup.py: add upper limit to prospector version


`v0.2.4`_ (2020-06-22)
^^^^^^^^^^^^^^^^^^^^^^

Miscellanea
"""""""""""

* Packaging: define a standard ``homer_plugins`` name for the external plugins and explicitely exclude them from the
  PyPI packaging.
* Removed support for Python version 3.5 and 3.6.

`v0.2.3`_ (2020-06-11)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* Improve error catching (`T253795`_).

  * For the diff action catch all the errors directly in the transport in order to return a consistent success and
    diff result for each device, skipping as a result those with failure. In case of failure return ``None`` so that
    it can be distinguished from an empty diff and reported as such both in logging and in the output.
  * For the commit action let the exceptions raise in the transport and be catched and logged in the main ``Homer``
    class with the same effective result that any failing device is skipped without interrupting the whole run.
  * In both cases log also the traceback when the debug logging is enabled.

`v0.2.2`_ (2020-05-06)
^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* netbox: adapt to new Netbox API

  * Netbox API starting with Netbox 2.8.0 have removed the choices API endpoint. Adapt the handling of the device
    status accordingly.


`v0.2.1`_ (2020-04-30)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""

* Add Python 3.8 support
* transports.junos: do not commit check on empty diff:

  * When performing a commit check, do not actually run the ``commit_check`` on the device if there is no diff.
  * In all cases perform a rollback, even on empty diff.

`v0.2.0`_ (2020-04-06)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* Handle commit abort separately (`T244362`_).

  * Introduce a new ``HomerAbortError`` exception to specifically handle cases in which the user explicitely aborted
    a write operation.
  * In the commit callback raise an ``HomerAbortError`` exception when the user abort the commit or reach the limit of
    invalid replies.

* transports.junos: retry when a timeout occurs during commits (`T244363`_).
* transports.junos: handle timeouts separately (`T244363`_).

  * Handle the ``RpcTimeoutError`` junos exception separately to avoid to have a full stacktrace in the logs as it's a
    normal failure scenario.
  * Handle the ``TimeoutExpiredError`` ncclient exception separately to avoid failures when calling ``close()``.

* allow overriding the ``ssh_config`` path in homer's config.
* plugins: initial implementation for Netbox data.

  * Allow to specify via configuration a Python module to load as a plugin for the Netbox data gathering.
  * When configured the plugin class is dynamically loaded and exposed to the templates as netbox.device_plugin.
  * It is basically the same implementation of ``NetboxDeviceData`` but allows for any specific selection of data from
    Netbox that is not generic enough to be included in Homer itself.

* commit: do not ``commit_check`` on initial empty diff.

  * As a consequence of commit ``1edb7c2`` if a device have an empty diff and a commit is run on it, it will run a
    ``commit_check`` anyway. Avoid this situation skipping the whole operation if at the first attempt the diff is
    empty.
  * In case of enough timeouts that don't allow Homer to complete the commit operation within the same run, the
    automatic rollback should be waited before retrying, otherwise the device will just be skipped.
  * To achieve this, passing the attempt number to all the operation callbacks, also if it's currently only used in
    the commit one to keep the same interface for all of them.

* diff: allow to omit the actual diff.

  * Add the ``-o/--omit-diff`` option to the ``diff`` sub-command to allow to omit the actual diff for security reasons
    if the diff results will be used for monitoring/alarming purposes, as the diff might contain sensitive data.

* diff: use different exit code if there is a diff (`T249224`_).

  * To allow to run automatic checks on outstanding diffs between the devices running configuration and the one defined
    in Homer's config and templates, make the diff command to return a different exit code when successfull but there
    is any diff.
  * In case of failure the failure exit code will prevail.

* netbox: silently skip devices without platform.

  * Some devices might not be reachable by default because not managed. Allow to more silently skip those (debug level
    logging only) if they are missing both the FQDN and the Platform in Netbox.

Minor improvements
""""""""""""""""""

* Sort deviced by FQDN
* netbox: skip virtual chassis devices without a domain field set, as they would not be reachable.

Miscellanea
"""""""""""

* examples: add comments to example config
* config: complete test coverage
* doc: fix example ``config.yaml`` indentation
* gitignore: add ``/plugins`` to gitignore to be able to link a plugin directory from other locations in a local
  checkout.

`v0.1.1`_ (2019-12-17)
^^^^^^^^^^^^^^^^^^^^^^

* Make the transport username configurable


`v0.1.0`_ (2019-12-17)
^^^^^^^^^^^^^^^^^^^^^^

* First release (`T228388`_).

.. _`Capirca documentation`: https://wikitech.wikimedia.org/wiki/Homer#Capirca_(ACL_generation)

.. _`gerrit/663535`: https://gerrit.wikimedia.org/r/c/operations/homer/public/+/663535

.. _`T228388`: https://phabricator.wikimedia.org/T228388
.. _`T244362`: https://phabricator.wikimedia.org/T244362
.. _`T244363`: https://phabricator.wikimedia.org/T244363
.. _`T249224`: https://phabricator.wikimedia.org/T249224
.. _`T253795`: https://phabricator.wikimedia.org/T253795
.. _`T257392`: https://phabricator.wikimedia.org/T257392
.. _`T260769`: https://phabricator.wikimedia.org/T260769
.. _`T273865`: https://phabricator.wikimedia.org/T273865

.. _`v0.1.0`: https://github.com/wikimedia/operations-software-homer/releases/tag/v0.1.0
.. _`v0.1.1`: https://github.com/wikimedia/operations-software-homer/releases/tag/v0.1.1
.. _`v0.2.0`: https://github.com/wikimedia/operations-software-homer/releases/tag/v0.2.0
.. _`v0.2.1`: https://github.com/wikimedia/homer/releases/tag/v0.2.1
.. _`v0.2.2`: https://github.com/wikimedia/homer/releases/tag/v0.2.2
.. _`v0.2.3`: https://github.com/wikimedia/homer/releases/tag/v0.2.3
.. _`v0.2.4`: https://github.com/wikimedia/homer/releases/tag/v0.2.4
.. _`v0.2.5`: https://github.com/wikimedia/homer/releases/tag/v0.2.5
.. _`v0.2.6`: https://github.com/wikimedia/homer/releases/tag/v0.2.6
.. _`v0.2.7`: https://github.com/wikimedia/homer/releases/tag/v0.2.7
.. _`v0.2.8`: https://github.com/wikimedia/homer/releases/tag/v0.2.8
.. _`v0.2.9`: https://github.com/wikimedia/homer/releases/tag/v0.2.9
.. _`v0.3.0`: https://github.com/wikimedia/homer/releases/tag/v0.3.0
.. _`v0.4.0`: https://github.com/wikimedia/homer/releases/tag/v0.4.0
