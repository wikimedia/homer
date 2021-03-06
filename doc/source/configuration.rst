Configuration
=============

.. _config.yaml:

config.yaml
-----------

The default configuration file for ``homer`` is expected to be found at ``/etc/homer/config.yaml``. Its path
can be changed in the CLI via the command-line switch ``-c/--config PATH``. A commented example configuration is
available in the source code at ``doc/examples/config.yaml`` and included here below:

.. literalinclude:: ../examples/config.yaml
   :language: yaml

The example file is also shipped, depending on the installation method, to:

* ``$VENV_PATH/share/doc/homer/examples/config.yaml`` when installed in a Python ``virtualenv`` via ``pip``.
* ``/usr/local/share/doc/homer/examples/config.yaml`` when installed globally via ``pip``.
* ``/usr/share/doc/homer/examples/config.yaml`` when installed via the Debian package.
