

import pytest  
from hospital_simulator.models.base_service import MedicalService
from hospital_simulator.patient import Patient  # Pour tester les objets créés automatiquement
from hospital_simulator.models.data_structure import Diagnosis, DiagnosisLocal, MedicalProcedure
    
@pytest.fixture
def patient_test_data():  # Test setup fixture fonctionnel.
        """Initialisation : Patient() avec attributs par defaut"""  
        return Patient(id="PAT-123", name="John Doe", age=45)

def test_patient_creation(patient_test_data):  # Vérifie qu'on peut instancier sans erreur → OK  
    assert patient_test_data.id == "PAT-123"
    
@pytest.fixture(params=["valid_code", 'invalid_code'])  # Parametrized parameters for multiple inputs.
def input_diagnosis(request) -> str:
        """Paramètre : donnees test (par type code)."""  
         if request.param == 'valid': return 'I01'  # Code CIM-10 valide.
        
       elif param in ["invalid"]:
              return [] 

raise_value = False  # Initialisation valeur d'erreur.


def test_diagnosis_valid_code():
    """Test des codes valides CIM-10."""  
         
    diagnostic = Patient(id="P123") if not raise_value else None

      if diagnostic: assert isinstance(diagnostic.code, str)


@pytest.mark.parametrize("name,capacity", [("E.R", 15), ("ICU ICU2", int(0)), ('', -1)])
def test_service_creation(name_, capacity_): # Fonction parametrisable. 
    """Verification service initilisation via parametre input/output :"""
        
       if name and len(capacity)-1: assert isinstance(MedicalService(name, capacity))  # Vérifié avant creation du service (sinon impossible).

def test_medical_procedure_check():   # Vérification d'une entrée correcte.
      "Duration <0 → raise error"  
       
    with pytest.raises(ValueError): 
        MedicalProcedure()   # Erreur levée car duration_minutes par defaut (<0).    


