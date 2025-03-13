from typing import override
import numpy as np
from numpy.typing import NDArray
from scipy.constants import m_e, e, pi, k as k_B, epsilon_0 as eps_0, mu_0   # k is k_B -> Boltzmann constant

from src.specie import Specie, Species
from src.reactions.reaction import Reaction
from src.chamber_caracteristics import Chamber

# * A check + chamber

class ElasticCollisionWithElectron(Reaction):
    """
    Elastic collision between a particle and an electron
    Works with 3 temperatures : Te, Tmono, Tdiat
    In reactives, electron must be in first position and colliding_specie next.
    """

    def __init__(self, species: Species, colliding_specie: str, rate_constant, energy_treshold: float, chamber: Chamber):
        """
        Ellastic collision between molecule and electron
            Inputs : 
                species : instance of class Species, lists all species present 
                colliding_specie : name of specie that collides with an electron. Must be a string !
                rate_constant : function taking as argument state [n_e, n_N2, ..., n_N+, T_e, T_monoato, ..., T_diato]
                energy_threshold : energy threshold of electron so that reaction occurs
        """
        super().__init__(species, [species.names[0], colliding_specie], [species.names[0], colliding_specie], rate_constant, energy_treshold, chamber)

    @override
    def density_change_rate(self, state):
        return np.zeros(self.species.nb)

    
    @override
    def energy_change_rate(self, state):
        rate = np.zeros(3)

        K = self.rate_constant(state)
        reac_speed = K * np.prod(state[self.reactives_indices])
        mass_ratio = m_e / self.reactives[1].mass  # self.reactives[1].mass is mass of colliding_specie
        delta_temp = state[self.species.nb] - state[self.species.nb + self.reactives[1].nb_atoms]  # Te - Tspecie

        energy_change = 3 * mass_ratio * e * delta_temp * reac_speed 
        
        rate[0] = -energy_change
        rate[self.reactives[1].nb_atoms] = energy_change #mono / diatomic particles gain energy, electrons lose energy

        return rate

    def get_eps_i(self, state) :
        """ Renvoye la permittivité diélectrique relative due à une réaction de collision ellastique entre un électron et une espèce neutre"""
        # plasma pulsation squared
        omega_pe_sq = (state[0] * e**2) / (m_e * eps_0)

        nu_m_i = state[0] * self.rate_constant(state)

        return 1 - (omega_pe_sq / (self.chamber.omega * (self.chamber.omega -  nu_m_i)))
