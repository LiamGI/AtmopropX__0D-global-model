from typing import override
import numpy as np
from numpy.typing import NDArray
from scipy.constants import m_e, e, pi, k as k_B, epsilon_0 as eps_0, mu_0   # k is k_B -> Boltzmann constant

from src.model_components.specie import Specie, Species
from src.model_components.reactions.reaction import Reaction
from src.model_components.chamber_caracteristics import Chamber


# * A check
# ! Valable uniquement pour Chabert
# ! Vérifier les surfaces : |   Je sais pas si j'ai pris les bonnes !!!!!

class FluxToWallsAndThroughGrids(Reaction):
    """
    Flux of electrons, ions and neutrals to the grids OR flux of ions and neutrals to the walls.
    Works with 3 temperatures : Te, Tmono, Tdiat
    In reactives, electron must be in first position and colliding_specie next.
    """

    def __init__(self, species: Species, colliding_specie: str, rate_constant, energy_treshold: float, chamber: Chamber):
        """
        FluxToWallsAndThroughGrids class
            Inputs : 
                species : instance of class Species, lists all species present 
                colliding_specie : name of specie that collides with an electron. Must be a string !
                rate_constant : function taking as argument state [n_e, n_N2, ..., n_N+, T_e, T_monoato, ..., T_diato]
                energy_threshold : energy threshold of electron so that reaction occurs
                chamber : chamber parameters of the chamber in which the reactions are taking place
        """
        super().__init__(species, [species.names[0], colliding_specie], [species.names[0], colliding_specie], chamber)
        self.rate_constant = rate_constant
        self.energy_treshold = energy_treshold

    @override
    def density_change_rate(self, state):
        rate = np.zeros(self.species.nb)
        n_g = 0
        gamma_e = 0
        #for i in range(len(state)/2) :
        for i in range(self.species.nb):
            #if self.specie.charge(self.species.species[i]) == 0:
            if self.species.species[i].charge==0:
                n_g += state[i]
        for sp in self.species.species[1:] :   # electron are skipped because handled before
            if sp.charge != 0:
                rate[sp.index] = - self.chamber.gamma_ion(state[sp.index], state[self.species.nb] , sp.mass) * self.chamber.S_eff_total_ion_neutrelisation(n_g) / self.chamber.V_chamber
                gamma_e += self.chamber.gamma_ion(state[sp.index], state[self.species.nb] , sp.mass)
            else:
                rate[sp.index] = - self.chamber.gamma_neutral(state[sp.index], state[self.species.nb + sp.nb_atoms], sp.mass) * self.chamber.S_eff_neutrals() / self.chamber.V_chamber
        rate[0] = - gamma_e * self.chamber.S_eff_total(n_g) / self.chamber.V_chamber
        return rate

    
    @override
    def energy_change_rate(self, state):

        rate = np.zeros(3)

        E_kin = 7*e*state[self.species.nb]

        
        n_g = 0
        #for i in(range(len(state)/2)) :
        for i in range(self.species.nb):
            #if self.specie.charge(self.species.species[i]) == 0:
            if self.species.species[i].charge==0:
                n_g += state[i]
        # * NOT neglected for now because missing energy of ion
        gamma_e = 0
        for sp in self.species.species[1:] :   # electron are skipped because handled before
            if sp.charge != 0:
                gamma_e += self.chamber.gamma_ion(state[sp.index], state[self.species.nb] , sp.mass)
            #     rate[sp.nb_atoms] = - self.chamber.gamma_ion(state[sp.index], state[self.species.nb] , sp.mass) * self.chamber.S_eff_total_ion_neutrelisation(n_g) / self.chamber.V_chamber
            else:
                E_neutral=sp.thermal_capacity * e * state[self.species.nb + sp.nb_atoms]
                rate[sp.nb_atoms] = - E_neutral * self.chamber.gamma_neutral(state[sp.index], state[self.species.nb + sp.nb_atoms] , sp.mass) * self.chamber.S_eff_neutrals() / self.chamber.V_chamber
        rate[0] = - E_kin * gamma_e * self.chamber.S_eff_total(n_g) / self.chamber.V_chamber
        return rate
    
    #problème avec les énergies : pour les ions, jsp mais pour les neutres: on prend l'agitation thermique
    #il faut distinguer mono et diato pour les capacités thermiques
