"""
Jython SAX 2.0 XML Parser
"""

import sys
for module in sys.modules:
    if module.endswith("ElementTree"):
        break
else:
    error  = "do not import this module directly, "
    error += "use 'import ElementTree' instead."
    raise ImportError(error)

# Jython 2.2 Standard Library
import StringIO
import types

# Java Standard Edition 6
import java.lang.String
import java.lang.System as System
import java.io.CharArrayReader
import org.xml.sax
import org.xml.sax.helpers

# ElementTree 1.3 alpha
import ElementTree

# New-style instances are not automatically clonable in Jython 2.2.
# We have to explicitely enable the shallow copy of elements.
def _copy_element(elt):
    clone = type("Element", (object,), {})()
    clone.__class__ = ElementTree.Element
    clone.__dict__.update(elt.__dict__)
    return clone

ElementTree.Element.__copy__ = _copy_element
Element = ElementTree.Element

# New-style classes and java classes can't be mixed with inheritance.
# The mixin approach is a simple workaround.
def mixin(base):
    attrs = dict(base.__dict__)
    methods = dict([attr for attr in attrs.items() if callable(attr[1])])
    def _mixin(target):
        for name, method in methods.items():
            try:
                getattr(target, name)
            except AttributeError:
                setattr(target, name, method)
        return target
    return _mixin

# TODO: use DefaultHandler instead ???
class XMLParser(org.xml.sax.ContentHandler, org.xml.sax.ErrorHandler): 
    # Mixin: ElementTree.XMLParser

 
    # TODO: clean up __init__ from the stuff that is not used.

    def __init__(self, html=0, target=None, encoding=None):
        if target is None:
            target = ElementTree.TreeBuilder()
        self.target = self._target = target

        self._buffer = StringIO.StringIO()
        self._doctype = None
        self.entity = {}
        self._names = {} # name memo cache

        XMLReader = org.xml.sax.helpers.XMLReaderFactory.createXMLReader
        self._reader = XMLReader()

        version = System.getProperties().getProperty("java.version");
        self.version = "J2SE %s" % version

        self._reader.setContentHandler(self)
        self._reader.setErrorHandler(self)
        self.parser = self._parser = self

        # Expat-like Callback Interface
        self.DefaultHandlerExpand      = self._default
        self.StartElementHandler       = self._start
        self.EndElementHandler         = self._end
        self.CharacterDataHandler      = self._data
        self.StartNamespaceDeclHandler = lambda *args: None
        self.EndNamespaceDeclHandler   = lambda *args: None

    # --- org.xml.sax.ErrorHandler Interface -------------------------------
    def fatalError(self, error):
        pass

    # --- org.xml.sax.ContentHandler Interface -----------------------------
    def startDocument(self):
        pass

    def endDocument(self):
        self._etree = self._target.close()

    def startElement(self, namespace, local_name, qname, attributes):
        tag = local_name
        if namespace:
            tag = namespace + "}" + tag
        attribs = {}
        length = attributes.getLength()
        for index in range(length):
            name = attributes.getLocalName(index)
            ns   = attributes.getURI(index)
            if ns:
                name = ns + "}" + name
            value = attributes.getValue(index)
            attribs[name] = value
        self.StartElementHandler(tag, attribs)

    def endElement(self, namespace, local_name, qualified_name):
        tag = local_name
        if namespace:
            tag = namespace + "}" + tag
        self.EndElementHandler(tag)

    def characters(self, characters, start, length):
        text = str(java.lang.String(characters[start:start+length]))
        self.CharacterDataHandler(text)

    def startPrefixMapping(self, prefix, uri):
        self.StartNamespaceDeclHandler(prefix, uri)

    def endPrefixMapping(self, prefix):
        self.EndNamespaceDeclHandler(prefix)

    def ignorableWhitespace(self, characters, start, length):
        pass

    def processingInstruction(self, target, data):
        pass

    def setDocumentLocator(self, locator):
        pass

    def skippedEntity(self, name):
        pass
    #-----------------------------------------------------------------------

    def _start_list(self, tag, attrib_in):
        return self._start(tag, attrib_in)

    def parse(self, text):
        self._reader.parse(text)

    def feed(self, data):
        self._buffer.write(data)

    _expat_error = {'The entity "entity" was referenced, but not declared.' :
                    "undefined entity: line %s, column %s"                  }

    def close(self):
        reader = java.io.CharArrayReader(self._buffer.getvalue())
        input_source = org.xml.sax.InputSource(reader)
        try:
            self.parse(input_source)
        except org.xml.sax.SAXParseException, jerror:
            # compensate for Expat 0-indexing for columns
            position = jerror.lineNumber, jerror.columnNumber-1
            try:
                message = self._expat_error.get(jerror.message) % position
            except:
                message = jerror.message
            error = ElementTree.ParseError(message)
            error.position = position
            error.code = None
            raise error

        return self._etree

XMLParser = mixin(ElementTree.XMLParser)(XMLParser)

ElementTree.XMLParser = XMLParser

