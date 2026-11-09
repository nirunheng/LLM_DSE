#include <iostream>
#include <vector>

#include "base/base.h"
#include "base/type.h"
#include "linear_mappers.h"


namespace Ramulator {


class ChRaBaRoCo final : public LinearMapperBase, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IAddrMapper, ChRaBaRoCo, "ChRaBaRoCo", "Applies a trival mapping to the address.");

  public:
    void init() override { };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      LinearMapperBase::setup(frontend, memory_system);
    }

    void apply(Request& req) override {
      req.addr_vec.resize(m_num_levels, -1);
      Addr_t addr = req.addr >> m_tx_offset;
      for (int i = m_addr_bits.size() - 1; i >= 0; i--) {
        req.addr_vec[i] = slice_lower_bits(addr, m_addr_bits[i]);
      }
    }
};


class RoBaRaCoCh final : public LinearMapperBase, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IAddrMapper, RoBaRaCoCh, "RoBaRaCoCh", "Applies a RoBaRaCoCh mapping to the address.");

  public:
    void init() override { };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      LinearMapperBase::setup(frontend, memory_system);
    }

    void apply(Request& req) override {
      req.addr_vec.resize(m_num_levels, -1);
      Addr_t addr = req.addr >> m_tx_offset;
      req.addr_vec[0] = slice_lower_bits(addr, m_addr_bits[0]);
      req.addr_vec[m_addr_bits.size() - 1] = slice_lower_bits(addr, m_addr_bits[m_addr_bits.size() - 1]);
      for (int i = 1; i <= m_row_bits_idx; i++) {
        req.addr_vec[i] = slice_lower_bits(addr, m_addr_bits[i]);
      }
    }
};


class MOP4CLXOR final : public LinearMapperBase, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IAddrMapper, MOP4CLXOR, "MOP4CLXOR", "Applies a MOP4CLXOR mapping to the address.");

  public:
    void init() override { };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      LinearMapperBase::setup(frontend, memory_system);
    }

    void apply(Request& req) override {
      req.addr_vec.resize(m_num_levels, -1);
      Addr_t addr = req.addr >> m_tx_offset;
      req.addr_vec[m_col_bits_idx] = slice_lower_bits(addr, 2);
      for (int lvl = 0 ; lvl < m_row_bits_idx ; lvl++)
          req.addr_vec[lvl] = slice_lower_bits(addr, m_addr_bits[lvl]);
      req.addr_vec[m_col_bits_idx] += slice_lower_bits(addr, m_addr_bits[m_col_bits_idx]-2) << 2;
      req.addr_vec[m_row_bits_idx] = (int) addr;

      int row_xor_index = 0; 
      for (int lvl = 0 ; lvl < m_col_bits_idx ; lvl++){
        if (m_addr_bits[lvl] > 0){
          int mask = (req.addr_vec[m_col_bits_idx] >> row_xor_index) & ((1<<m_addr_bits[lvl])-1);
          req.addr_vec[lvl] = req.addr_vec[lvl] xor mask;
          row_xor_index += m_addr_bits[lvl];
        }
      }
    }
};


// Ch is inserted into RoBaRaCo, the lowest bit of Ch is indicated by m_channel_lowest_bit
class OneLevelInterleave final : public LinearMapperBase, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IAddrMapper, OneLevelInterleave, "OneLevelInterleave", "Applies a one level interleave mapping to the address.");

  int m_channel_lowest_bit = -1; // NOTE: This value excludes the bit number of m_tx_offset
  int m_channel_highest_bit = -1;
  int m_channel_lower_value_mask = 0;
  int m_channel_value_mask = 0;

  public:
    void init() override {
      if(m_config["channel_lowest_bit"]) {
        m_channel_lowest_bit = m_config["channel_lowest_bit"].as<int>();
      }
      else {
        std::cout << "[WARNING] channel_lowest_bit is not specified in the config file." << std::endl;
        std::cout << "          Using default mapping RoBaRaCoCh (i.e., channel_lowest_bit = 0)." << std::endl;
        m_channel_lowest_bit = 0;
      }
    };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      LinearMapperBase::setup(frontend, memory_system);

      m_channel_highest_bit = m_channel_lowest_bit + m_addr_bits[0] - 1;
      m_channel_lower_value_mask = (1 << m_channel_lowest_bit) - 1;
      m_channel_value_mask = (1 << m_addr_bits[0]) - 1;
    }

    Addr_t get_ch_offset() override {
      return m_channel_lowest_bit;
    }

    void apply(Request& req) override {
      req.addr_vec.resize(m_num_levels, -1);

      // First remove m_tx_offset
      Addr_t addr = req.addr >> m_tx_offset;

      // Then extract channel value
      req.addr_vec[0] = (addr >> m_channel_lowest_bit) & m_channel_value_mask;

      // Remove channel bits, convert from [High][Ch][Low] to [High][Low] in bit representation
      Addr_t remaining_addr = ((addr >> (m_channel_highest_bit+1)) << m_channel_lowest_bit)
                            | (addr & m_channel_lower_value_mask);
      
      // The remaining process is identical to RoBaRaCoCh
      req.addr_vec[m_addr_bits.size() - 1] = slice_lower_bits(remaining_addr, m_addr_bits[m_addr_bits.size() - 1]);
      for (int i = 1; i <= m_row_bits_idx; i++) {
        req.addr_vec[i] = slice_lower_bits(remaining_addr, m_addr_bits[i]);
      }
    }
};


}   // namespace Ramulator