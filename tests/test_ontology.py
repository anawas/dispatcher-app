import pytest
import rdflib as rdf
from rdflib.namespace import XSD
from rdflib.compare import isomorphic
from cdci_data_analysis.analysis.ontology import Ontology
from cdci_data_analysis.analysis.exceptions import RequestNotUnderstood

oda_prefix = 'http://odahub.io/ontology#'
xsd_prefix = 'http://www.w3.org/2001/XMLSchema#'
add_prefixes = """
            @prefix oda: <http://odahub.io/ontology#> . 
            @prefix unit: <http://odahub.io/ontology/unit#> . 
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . 
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            """
ontology_path = 'oda-ontology.ttl'

@pytest.fixture
def onto(scope='module'):
    return Ontology(ontology_path)

def test_ontology_hierarchy(onto):
    hierarchy_list = onto.get_parameter_hierarchy('oda:PointOfInterestRA')
    assert f'{oda_prefix}RightAscension' in hierarchy_list
    assert hierarchy_list.index(f'{oda_prefix}PointOfInterestRA') < \
           hierarchy_list.index(f'{oda_prefix}RightAscension') < \
           hierarchy_list.index(f'{oda_prefix}Angle') < \
           hierarchy_list.index(f'{oda_prefix}Float') 
           
    hierarchy_list = onto.get_parameter_hierarchy('oda:Energy_keV')
    assert f'{oda_prefix}Energy' in hierarchy_list
    assert hierarchy_list.index(f'{oda_prefix}Energy_keV') < hierarchy_list.index(f'{oda_prefix}Float')


@pytest.mark.parametrize('owl_uri', ['http://www.w3.org/2001/XMLSchema#bool', 'http://odahub.io/ontology#Unknown'])
def test_ontology_unknown(onto, owl_uri, caplog):
    hierarchy_list = onto.get_parameter_hierarchy(owl_uri)
    assert hierarchy_list == [owl_uri]
    assert f"{owl_uri} is not in ontology or not an oda:WorkflowParameter" in caplog.text
    
    
@pytest.mark.parametrize("owl_uri,expected,extra_ttl,return_uri", 
                         [('oda:StartTimeMJD', f'{oda_prefix}MJD', None, True),
                          ('oda:StartTimeISOT', 'isot', None, False),
                          ('oda:TimeInstant', None, None, False),
                          ('http://odahub.io/ontology#Unknown', None, None, False),
                          ('oda:foo', 'mjd', """@prefix oda: <http://odahub.io/ontology#> . 
                                                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . 
                                                oda:foo rdfs:subClassOf oda:TimeInstant ; 
                                                        oda:format oda:MJD . """, False)
                          ])
def test_ontology_format(onto, owl_uri, expected,extra_ttl, return_uri):
    if extra_ttl is not None:
        onto.parse_extra_ttl(extra_ttl)
    format = onto.get_parameter_format(owl_uri, return_uri=return_uri)
    assert format == expected
    
@pytest.mark.parametrize("owl_uri, expected, extra_ttl, return_uri",
                         [('oda:TimeDays', f'{oda_prefix}Day', None, True),
                          ('oda:DeclinationDegrees', 'deg', None, False),
                          ('oda:Energy', None, None, False),
                          ('http://odahub.io/ontology#Unknown', None, None, False),
                          ('oda:spam', 's', """@prefix oda: <http://odahub.io/ontology#> . 
                                               @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . 
                                               oda:spam rdfs:subClassOf oda:TimeDelta, oda:par_second . """, False),
                          ('oda:eggs', 'h', """@prefix oda: <http://odahub.io/ontology#> . 
                                               oda:eggs a oda:TimeDelta ;
                                                        oda:unit oda:Hour . """, False)
                         ])
def test_ontology_unit(onto, owl_uri, expected, extra_ttl, return_uri):
    if extra_ttl is not None:
        onto.parse_extra_ttl(extra_ttl)
    unit = onto.get_parameter_unit(owl_uri, return_uri=return_uri)
    assert unit == expected
    
def test_ambiguous_unit(onto):
    onto.parse_extra_ttl("""@prefix oda: <http://odahub.io/ontology#> .
                            @prefix rdfs: <rdfs	http://www.w3.org/2000/01/rdf-schema#> .
                            oda:Energy_EeV a oda:Energy_TeV ;
                                           oda:unit oda:EeV .""")
    with pytest.raises(RequestNotUnderstood):
        onto.get_parameter_unit('oda:Energy_EeV')

    
@pytest.mark.parametrize("owl_uri, expected, extra_ttl",
                         [('oda:Float', (None, None), ""),
                          ('http://odahub.io/ontology#Unknown', (None, None), ""),
                          ('oda:ISGRIEnergy', (15, 800), ""), # Individual 
                          ('oda:Percentage', (0, 100), ""), # Class
                          ('oda:Float_w_lim', (0, 1), """@prefix oda: <http://odahub.io/ontology#> .
                                                         oda:Float_w_lim a oda:Float ;
                                                                    oda:lower_limit 0 ;
                                                                    oda:upper_limit 1 ."""),
                         ])
def test_ontology_limits(onto, owl_uri, expected, extra_ttl):
    if extra_ttl is not None:
        onto.parse_extra_ttl(extra_ttl)
    limits = onto.get_limits(owl_uri)
    assert limits == expected
    
def test_ontology_redefined_limits(onto, caplog):
    onto.parse_extra_ttl("""@prefix oda: <http://odahub.io/ontology#> .
                            oda:second_quartile a oda:Percentage ;
                                                oda:lower_limit 25 ;
                                                oda:upper_limit 50 .""")
    # strictly speaking, this is inconsistent definition, but let's allow it
    limits = onto.get_limits('oda:second_quartile')
    assert limits == (25, 50)
    assert 'Ambiguous lower_limit, using the most restrictive' in caplog.text
    assert 'Ambiguous upper_limit, using the most restrictive' in caplog.text
    
@pytest.mark.parametrize("owl_uri, expected, extra_ttl",
                         [('oda:String', None, None),
                          ('oda:PhotometricBand', ['b', 'g', 'H', 'i', 'J', 'K', 'L', 'M', 'N', 'Q', 'r', 'u', 'v', 'y', 'z'], None),
                          ('oda:LegacySurveyBand', ['r', 'g', 'z'], None),
                          ('oda:custom', ['a', 'b'], """@prefix oda: <http://odahub.io/ontology#> .
                                                        oda:custom a oda:String ;
                                                                   oda:allowed_value "a" ;
                                                                   oda:allowed_value "b" .""")
                         ])
def test_ontology_allowed_values(onto, owl_uri, expected, extra_ttl):
    if extra_ttl is not None:
        onto.parse_extra_ttl(extra_ttl)
    allowed_values = onto.get_allowed_values(owl_uri)
    assert allowed_values == expected

@pytest.mark.parametrize("par_uri, datatype",
                         [('oda:Integer', XSD.integer),
                          ('oda:Float', XSD.float),
                          ('oda:Percentage', XSD.float),
                          ('oda:Energy_keV', XSD.float),
                          ('xsd:string', XSD.string),
                          ('oda:Unknown', None),
                          ])
def test_datatype_restriction(onto, par_uri, datatype):
    assert onto._get_datatype_restriction(par_uri) == datatype
        
     
def test_parsing_unit_annotation(onto):
    g, g_expect = rdf.Graph(), rdf.Graph()
    annotated_ttl = add_prefixes + """
        oda:someEnergy rdfs:subClassOf oda:Energy ;
                    oda:unit    unit:keV .
        """ 
    g.parse(data = annotated_ttl)
    
    expected = annotated_ttl + """
        oda:someEnergy rdfs:subClassOf [
                    a owl:Restriction ;
                    owl:onProperty oda:has_unit ;
                    owl:hasValue unit:keV 
                    ] .
        """
    g_expect.parse(data = expected)
    
    onto.parse_oda_annotations(g)
    
    assert isomorphic(g, g_expect)
    
    with pytest.raises(RuntimeError):
        annotated_ttl = add_prefixes + """
            oda:someEnergy rdfs:subClassOf oda:Energy ;
                        oda:unit    unit:keV ;
                        oda:unit    unit:MeV .
            """ 
        g.parse(data = annotated_ttl)
        onto.parse_oda_annotations(g)
    
def test_parsing_format_annotation(onto):
    g, g_expect = rdf.Graph(), rdf.Graph()
    annotated_ttl = add_prefixes + """
        oda:someTime rdfs:subClassOf oda:TimeInstant ;
                    oda:format    oda:ISOT .
        """ 
    g.parse(data = annotated_ttl)
    
    expected = annotated_ttl + """
        oda:someTime rdfs:subClassOf [
                    a owl:Restriction ;
                    owl:onProperty oda:has_format ;
                    owl:hasValue oda:ISOT 
                    ] .
        """
    g_expect.parse(data = expected)
    
    onto.parse_oda_annotations(g)
    
    assert isomorphic(g, g_expect)
    
    with pytest.raises(RuntimeError):
        annotated_ttl = add_prefixes + """
            oda:someTime rdfs:subClassOf oda:TimeInstant ;
                    oda:format    oda:ISOT ;
                    oda:format    oda:MJD . 
            """ 
        g.parse(data = annotated_ttl)
        onto.parse_oda_annotations(g)
    
def test_parsing_allowedval_annotation(onto):
    g, g_expect = rdf.Graph(), rdf.Graph()
    annotated_ttl = add_prefixes + """
        oda:someString rdfs:subClassOf oda:String ;
                    oda:allowed_value  "a", "b", "c" .
        """ 
    g.parse(data = annotated_ttl)
    
    expected = annotated_ttl + """
        oda:someString rdfs:subClassOf [
                    a owl:Restriction ;
                    owl:onProperty oda:value ;
                    owl:allValuesFrom [
                        a rdfs:Datatype ;
                        owl:oneOf ("a" "b" "c") ] 
                    ] .
        """
    g_expect.parse(data = expected)
    
    onto.parse_oda_annotations(g)
    
    assert isomorphic(g, g_expect)
    
@pytest.mark.parametrize("input_ttl, expected_restr",
                         [("""oda:someFloat rdfs:subClassOf oda:Float ;
                                            oda:lower_limit  0 .
                           """,
                           """oda:someFloat rdfs:subClassOf [
                                    a owl:Restriction ;
                                    owl:onProperty oda:value ;
                                    owl:allValuesFrom [
                                        a rdfs:Datatype ;
                                        owl:onDatatype xsd:float ;
                                        owl:withRestrictions ( [xsd:minInclusive "0.0"^^xsd:float ] )
                                        ] 
                                    ] . 
                           """)
                             #TODO: more tests
                         ]) 
def test_parsing_limits_annotation(onto, input_ttl, expected_restr):
    g, g_expect = rdf.Graph(), rdf.Graph()
    annotated_ttl = add_prefixes + input_ttl
    g.parse(data = annotated_ttl)
    
    expected = annotated_ttl + expected_restr
    g_expect.parse(data = expected)
    
    onto.parse_oda_annotations(g)
    
    assert isomorphic(g, g_expect)
    

def test_parsing_lower_limit_multiple_exception(onto):
    g = rdf.Graph()
    with pytest.raises(RuntimeError):
        annotated_ttl = add_prefixes + """
            oda:someFloat rdfs:subClassOf oda:Float ;
                    oda:lower_limit   1.0 ;
                    oda:lower_limit   1.1 . 
            """ 
        g.parse(data = annotated_ttl)
        onto.parse_oda_annotations(g)

def test_parsing_upper_limit_multiple_exception(onto):
    g = rdf.Graph()
    with pytest.raises(RuntimeError):
        annotated_ttl = add_prefixes + """
            oda:someFloat rdfs:subClassOf oda:Float ;
                    oda:upper_limit   1.0 ;
                    oda:upper_limit   1.1 . 
            """ 
        g.parse(data = annotated_ttl)
        onto.parse_oda_annotations(g)