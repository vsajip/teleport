Teleport
========

Teleport is a lightweight type system that extends JSON. It can be used for:

* Serializing data
* Validating input
* Generating documentation
* Building custom JSON serializers
* Building API clients

Teleport is:

* Portable and extendable
* Open Source ([MIT license](http://opensource.org/licenses/MIT))

Status
======

The latest [specification](http://www.teleport-json.org/spec/latest/) has been
submitted as [an Internet Draft](https://datatracker.ietf.org/doc/draft-boronine-teleport/)
on Dec 5, 2014. It is implemented as a [Python library](http://www.teleport-json.org/python/latest/).

Build Instructions
==================

Install requirements (in project root):

    sudo pip install sphinx, xml2rfc
    npm install

Create Makefile:

	./configure

To build full site:

	make .cache/site.tar

To build Python docs from current tree:

	make .cache/current-source-sphinx.tar

To clear cache:

	make clean

To deploy via rsync (private key):

	make .cache/site-inject.tar
	make deploy

Live development mode (site, Python docs, spec):

	./live site
	./live current-source-sphinx
	./live current-source-xml2rfc

License
-------

Copyright (C) 2014 8313547 Canada Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
