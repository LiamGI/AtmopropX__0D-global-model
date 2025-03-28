import numpy as np 
from numpy.typing import NDArray
from scipy.constants import m_e, e, pi, k, epsilon_0 as eps_0, mu_0, c as c_light   # k is k_B -> Boltzmann constant
from scipy.integrate import trapezoid, solve_ivp, odeint
from scipy.interpolate import interp1d
from scipy.optimize import fsolve
from scipy.special import jv
import json
import os
import warnings

#Local modules
from src.model_components.util import load_csv, load_cross_section
# from src.auxiliary_funcs import pressure, maxwellian_flux_speed, u_B, A_eff, A_eff_1, SIGMA_I, h_L
from src.model_components.specie import Specie, Species
from src.model_components.reactions.reaction import Reaction
from src.model_components.reactions.general_elastic_collision import GeneralElasticCollision
from src.model_components.reactions.electron_heating_by_coil_reaction import ElectronHeatingConstantAbsorbedPower, ElectronHeating
from src.model_components.chamber_caracteristics import Chamber

log_folder_path = "./logs"

class GlobalModel:

    def __init__(self, species: Species, reaction_set: list[Reaction], chamber: Chamber, simulation_name: str = "test_simu", electron_heating: ElectronHeating = None):
        """Object simulating the evolution of a plasma with 0D model. 
            Inputs :
                config_dict : dictionary containing all parameters about the experimental setup
                species : instance of Species with all species being considered
                reaction_set : list with all reactions being considered -> [Reaction]"""
        self.species = species
        self.reaction_set = reaction_set
        self.chamber = chamber
        self.simulation_name = simulation_name
        self.tracked_variables = {}
        if electron_heating is None:
            warnings.warn("No electron heating reaction was provided")
            self.electron_heating = ElectronHeatingConstantAbsorbedPower(species, 0, chamber)
        else:
            self.electron_heating = electron_heating    


    def eval_property(self, func, sol):
        """Calculates a property based on 'state' for all 't'.
            sol must be a np.array with shape (nb_of_t's, dimension_of_state) where each line represents a state"""
        prop = np.zeros(sol.shape[0])   #number of instants
        for i in np.arange(sol.shape[0]):
            prop[i] = func(sol[i])
        return prop       
    
    def f_dy(self, t, state):
        """Returns the derivative of the vector 'state' describing the state of plasma.
            'state' has format : [n_e, n_N2, ..., n_N+, T_e, T_monoato, ..., T_diato]"""
        densities = state[:self.species.nb]
        temp = state[self.species.nb:]

        dy = np.zeros(state.shape)
        dy_densities = np.zeros(self.species.nb)
        dy_energies = np.zeros(3)

        collision_frequencies = np.zeros(self.species.nb)
        for reac in self.reaction_set:
            dy_densities += reac.density_change_rate(state)
            dy_energies += reac.energy_change_rate(state)
            if isinstance(reac, GeneralElasticCollision) :
                sp_idx, freq = reac.colliding_specie_and_collision_frequency(state)
                collision_frequencies[sp_idx] += freq
        eps_p = self.eps_p(collision_frequencies, state)

        # calculation of P_abs : the power given by the antenna to the plasma
        #self.P_abs(self.R_ind( eps_p  ))

        # Energy given to the electrons via the coil
        dy_energies += self.electron_heating.absorbed_power(state, collision_frequencies)   #self.P_abs(self.R_ind( eps_p  ))

        for i in range(3):
            self.add_value_to_variable("dy_energy_"+str(i), dy_energies[i])
        # total thermal capacity of all species with same number of atoms : sum of (3/2 or 5/2 * density)
        total_thermal_capacity_by_sp_type = np.zeros(3)
        dy_total_thermal_capacity_by_sp_type = np.zeros(3)
        for sp in self.species.species :
            total_thermal_capacity_by_sp_type[sp.nb_atoms] += sp.thermal_capacity * densities[sp.index]
            dy_total_thermal_capacity_by_sp_type[sp.nb_atoms] += sp.thermal_capacity * dy_densities[sp.index]
        
        #Transform derivative of energy into derivative of temperature
        dy_temp = (dy_energies - temp * dy_total_thermal_capacity_by_sp_type) / total_thermal_capacity_by_sp_type

        dy[:self.species.nb] = dy_densities
        dy[self.species.nb:] = np.nan_to_num(dy_temp, nan=0.0)

        self.add_value_to_variable("time", t)
        self.add_densities_and_temperature(state)
        self.add_densities_and_temperature(dy, prefix="dy_")
        self.add_value_to_variable("eps_p_real", np.real(eps_p))
        self.add_value_to_variable("eps_p_imag", np.imag(eps_p))

        return dy
    
    


    def thrust_i(self, T_e, n_e, n_ion , m_ion , charge):
        """Thrust produced by the ion beam of one specie"""
        return self.chamber.gamma_ion(n_ion, T_e , m_ion) * specie.mass * self.chamber.v_beam(m_ion , charge) * self.chamber.beta_i * pi * self.chamber.R ** 2

    def j_i(self, T_e, n_e, n_ion , m_ion , charge):
        """Ion current density of one ionic specie extracted by the grids"""
        return self.chamber.gamma_ion( n_ion, T_e, m_ion) * e * charge

        
    def total_ion_thrust(self , state ) :
        '''Calculates the total amount of thrust generated'''
        total_thrust = 0
        for i in(range(1,len(state)/2)):
            if self.species.species[i].charge != 0 :
                total_thrust += self.thrust_i( state[len(state)/2] , state[0] , state[i] , slef.species.species[i].mass , self.species.species[i].charge)


    def total_ion_current(self , state ) :
        '''Calculates the total amount of ion current toxards the grids'''
        total_current = 0
        for i in(range(1,len(state)/2)):
            if self.species.species[i].charge != 0 :
                total_current += self.j_i( state[len(state)/2] , state[0] , state[i] , self.species.species[i].mass , self.species.species[i].charge)
        return total_current

    def n_g (self, state) :
        '''total density of neutral gases'''
        total = 0
        for i in(range(len(state)/2)) :
            if self.specie.charge(self.species.species[i]) == 0 :
                total += state[i]
        return total
        
    def solve(self, t0, tf):
        y0 = np.array([self.chamber.n_e_0, self.chamber.n_g_0, 0, self.chamber.T_e_0, self.chamber.T_g_0, -1])
        sol = solve_ivp(self.f_dy, (t0, tf), y0, method='LSODA')
        self.save_tracked_variables(self.simulation_name+".json")
        return sol


    def solve_for_I_coil(self, coil_currents, tf = 5e-2):
        """Calculates for a list of intensity in the coil the resulting power consumption and the resulting thrust.
            ## Returns
            power_array , list_of(`state` after long time)"""
        power_array = np.zeros(coil_currents.shape[0])
        final_states = np.zeros((coil_currents.shape[0], self.species.nb+3))  #shape = (y,x)

        for i, I_coil in enumerate(coil_currents):
            self.chamber.I_coil = I_coil

            sol = self.solve(0, tf)    # TODO Needs some testing

            final_state = sol.y[:, -1]

            collision_frequencies = np.zeros(self.species.nb)
            for reac in self.reaction_set:
                if isinstance(reac, GeneralElasticCollision) :
                    sp_idx, freq = reac.colliding_specie_and_collision_frequency(final_state)
                    collision_frequencies[sp_idx] = freq
            eps_p = self.eps_p(collision_frequencies, final_state)

            # calculation of P_abs : the power given by the antenna to the plasma

            power_array[i] = self.electron_heating.absorbed_power(final_state, collision_frequencies)   #self.P_abs(self.R_ind( eps_p  ))

            final_states[i] = final_state
            
        return power_array, final_states
    

    
