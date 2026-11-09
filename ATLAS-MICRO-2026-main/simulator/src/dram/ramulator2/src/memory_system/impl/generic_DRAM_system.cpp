#include "base/type.h"
#include "memory_system/memory_system.h"
#include "translation/translation.h"
#include "dram_controller/controller.h"
#include "addr_mapper/addr_mapper.h"
#include "dram/dram.h"

namespace Ramulator {

class GenericDRAMSystem final : public IMemorySystem, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IMemorySystem, GenericDRAMSystem, "GenericDRAM", "A generic DRAM-based memory system.");

  protected:
    Clk_t m_clk = 0;
    IDRAM*  m_dram;
    IAddrMapper*  m_addr_mapper;
    std::vector<IDRAMController*> m_controllers;

  public:
    int s_num_read_requests = 0;
    int s_num_write_requests = 0;
    int s_num_other_requests = 0;


  public:
    void init() override { 
      // Create device (a top-level node wrapping all channel nodes)
      m_dram = create_child_ifce<IDRAM>();
      m_addr_mapper = create_child_ifce<IAddrMapper>();

      int num_channels = m_dram->get_level_size("channel");   

      // Create memory controllers
      for (int i = 0; i < num_channels; i++) {
        IDRAMController* controller = create_child_ifce<IDRAMController>();
        controller->m_impl->set_id(fmt::format("Channel {}", i));
        controller->m_channel_id = i;
        m_controllers.push_back(controller);
      }

      m_clock_ratio = param<uint>("clock_ratio").default_val(1);

      register_stat(m_clk).name("memory_system_cycles");
      register_stat(s_num_read_requests).name("total_num_read_requests");
      register_stat(s_num_write_requests).name("total_num_write_requests");
      register_stat(s_num_other_requests).name("total_num_other_requests");
    };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override { }

    bool send(Request req) override {
      m_addr_mapper->apply(req);
      int channel_id = req.addr_vec[0];
      bool is_success = m_controllers[channel_id]->send(req);

      if (is_success) {
        switch (req.type_id) {
          case Request::Type::Read: {
            s_num_read_requests++;
            break;
          }
          case Request::Type::Write: {
            s_num_write_requests++;
            break;
          }
          default: {
            s_num_other_requests++;
            break;
          }
        }
      }

      return is_success;
    };
    
    void tick() override {
      m_clk++;
      m_dram->tick();
      for (auto controller : m_controllers) {
        controller->tick();
      }
    };

    // The unit is GB/s
    double get_max_bw() override {
      // (1) BW = tx_bytes / (nBL * tCK)
      double tx_bytes = m_dram->m_internal_prefetch_size * m_dram->m_channel_width / 8.0;
      double BL_ns = m_dram->m_timing_vals("nBL") * m_dram->m_timing_vals("tCK_ps") / 1000.0;
      double BW1 = tx_bytes / BL_ns;

      // (2) BW = DQ * rate / 8
      double DQ = m_dram->m_organization.dq;
      double rate_Gbps = m_dram->m_timing_vals("rate") / 1000.0;
      double BW2 = DQ * rate_Gbps / 8.0;

      assert(std::abs(BW1 - BW2) < 1e-6);

      int channel_num = m_dram->get_level_size("channel");
      return BW1 * channel_num;
    }

    float get_tCK() override {
      return m_dram->m_timing_vals("tCK_ps") / 1000.0f;
    }

    int get_clk() override {
      return m_clk;
    }

    int get_channel_num() override {
      return m_controllers.size();
    }

    // The unit is byte
    Addr_t get_row_size() override {
      return m_dram->m_organization.count[m_dram->m_levels("column")] * m_dram->m_organization.dq / 8;
    }

    IAddrMapper* get_addr_mapper() override {
      return m_addr_mapper;
    }

    bool is_finished() override {
      for (auto controller : m_controllers) {
        if (!controller->is_finished())
          return false;
      }
      return true;
    }

    // const SpecDef& get_supported_requests() override {
    //   return m_dram->m_requests;
    // };
};
  
}   // namespace 

