#ifndef     RAMULATOR_FRONTEND_FRONTEND_H
#define     RAMULATOR_FRONTEND_FRONTEND_H

#include <vector>
#include <string>
#include <functional>

#include "base/base.h"
#include "base/type.h"
#include "memory_system/memory_system.h"

#include "common/data.h"
#include "core/component.h"


namespace Ramulator {


typedef atlasim::ComponentInput HBInput;


class IFrontEnd : public Clocked<IFrontEnd>, public TopLevel<IFrontEnd> {
  RAMULATOR_REGISTER_INTERFACE(IFrontEnd, "Frontend", "The frontend that drives the simulation.");

  friend class Factory;

  protected:
    IMemorySystem* m_memory_system = nullptr;
    uint m_clock_ratio = 1;

  public:
    virtual void connect_memory_system(IMemorySystem* memory_system) { 
      m_memory_system = memory_system; 
      m_impl->setup(this, memory_system);
      for (auto component : m_components) {
        component->setup(this, memory_system);
      }
    };

    virtual bool is_finished() = 0;

    virtual void finalize() { 
      for (auto component : m_components) {
        component->finalize();
      }

      YAML::Emitter emitter;
      emitter << YAML::BeginMap;
      m_impl->print_stats(emitter);
      emitter << YAML::EndMap;
      std::cout << emitter.c_str() << std::endl;
    };

    virtual int get_num_cores() { return 1; };

    int get_clock_ratio() { return m_clock_ratio; };

    /**
     * @brief    Receives memory requests from external sources (e.g., coming from a full system simulator like GEM5)
     * 
     * @details
     * This functions should take memory requests from external sources (e.g., coming from GEM5), generate Ramulator 2 Requests,
     * (tries to) send to the memory system, and return if this is successful
     * 
     */
    virtual bool receive_external_requests(int req_type_id, Addr_t addr, int source_id, std::function<void(Request&)> callback) { return false; }

    /**
     * Used for Hybrid Bonding DRAM's frontend
     */
    // Get necessary information for request generation
    virtual void set_memory_system_info() { }
    virtual Addr_t get_tx_bytes() { return 0; }
    virtual Addr_t get_ch_offset() { return 0; }
    // This function takes high-level MemoryAccess transactions from ATLAS simulator's "PE core --> DRAM wrapper" path,
    // then translates each tensor tile's access to ramulator requests.
    // Return value: Generated DRAM instruction number 
    virtual int send(HBInput input) { return 0; }
    // Get current tile's read bytes and write bytes
    virtual int get_read_bytes() { return 0; }
    virtual int get_write_bytes() { return 0; }
    // Get all tiles' read bytes and write bytes;
    virtual int get_total_read_bytes() { return 0; }
    virtual int get_total_write_bytes() { return 0; }
    
};

}        // namespace Ramulator


#endif   // RAMULATOR_FRONTEND_FRONTEND_H