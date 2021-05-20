"""
Overview
--------

general info about this module


Classes and Inheritance Structure
----------------------------------------------
.. inheritance-diagram::

Summary
---------
.. autosummary::
   list of the module you want

Module API
----------
"""

from __future__ import absolute_import, division, print_function

__author__ = "Andrea Tramacere"

# Standard library
# eg copy
# absolute import rg:from copy import deepcopy

# Dependencies
# eg numpy
# absolute import eg: import numpy as np

# Project
# relative import eg: from .mod import f


from cdci_data_analysis.analysis.instrument import Instrument
from cdci_data_analysis.analysis.queries import SourceQuery, InstrumentQuery, Float, QueryOutput

from .data_server_dispatcher import DataServerQuerySemiAsync, EmptyProductQuery, DataServerNumericQuery


def my_instr_factory():
    src_query = SourceQuery('src_query')

    # empty query
    instr_query = InstrumentQuery(name='empty_async_instrument_query',)

    # my_instr_image_query -> name given to this query
    empty_query = EmptyProductQuery('empty_parameters_dummy_query',)
    # let's build a simple parameter to its list
    p = Float(value=10., name='p', units='W',)
    numerical_query = DataServerNumericQuery('numerical_parameters_dummy_query',
                                             parameters_list=[p])

    # this dicts binds the product query name to the product name from frontend
    # eg my_instr_image is the parameter passed by the fronted to access the
    # the MyInstrMosaicQuery, and the dictionary will bind
    # query_dictionary['my_instr_image'] = 'my_instr_image_query'
    query_dictionary = {}
    # the empty instrument does not effectively do anything and therefore support any particular query
    # nor product, only a simple query that does not return anything
    query_dictionary['dummy'] = 'empty_parameters_dummy_query'
    query_dictionary['numerical'] = 'numerical_parameters_dummy_query'

    return Instrument('empty-semi-async',
                      src_query=src_query,
                      instrumet_query=instr_query,
                      product_queries_list=[empty_query, numerical_query],
                      query_dictionary=query_dictionary,
                      data_server_query_class=DataServerQuerySemiAsync)