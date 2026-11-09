#include "dram/dram.h"
#include "dram/lambdas.h"

namespace Ramulator {

class HBDRAM : public IDRAM, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IDRAM, HBDRAM, "HBDRAM", "Hybrid-Bonding DRAM Device Model")

  public:
    inline static const std::map<std::string, Organization> org_presets = {
      //      name        density   DQ    Ch Bg Ba    Ro    Co
      {"HBDRAM_4Gb_1024pin",   {1<<12,  1024,  {1, 1, 1, 1<<15, 1<<7}}},
      // Used for channel organization exploration
      {"HBDRAM_2Gb_512pin",   {1<<11,  512,  {1, 1, 1, 1<<14, 1<<8}}},
      {"HBDRAM_1Gb_256pin",   {1<<10,  256,  {1, 1, 1, 1<<13, 1<<9}}},
      {"HBDRAM_8Gb_2048pin",   {1<<13,  2048,  {1, 1, 1, 1<<16, 1<<6}}},
      {"HBDRAM_16Gb_4096pin",   {1<<14,  4096,  {1, 1, 1, 1<<17, 1<<5}}},
      {"HBDRAM_32Gb_8192pin",   {1<<15,  8192,  {1, 1, 1, 1<<18, 1<<4}}},
      // Used for bank organization exploration
      {"HBDRAM_4Gb_1024pin_256col",   {1<<12,  1024,  {1, 1, 1, 1<<14, 1<<8}}},
      {"HBDRAM_4Gb_1024pin_512col",   {1<<12,  1024,  {1, 1, 1, 1<<13, 1<<9}}},
      {"HBDRAM_4Gb_1024pin_64col",   {1<<12,  1024,  {1, 1, 1, 1<<16, 1<<6}}},
      {"HBDRAM_4Gb_1024pin_32col",   {1<<12,  1024,  {1, 1, 1, 1<<17, 1<<5}}},
      {"HBDRAM_4Gb_1024pin_16col",   {1<<12,  1024,  {1, 1, 1, 1<<18, 1<<4}}},
      // Used for full space e2e exploration
      {"HBDRAM_2Gb_512pin_32KB",   {1<<11,  512,  {1, 1, 1, 1<<13, 1<<9}}},
      {"HBDRAM_2Gb_512pin_64KB",   {1<<11,  512,  {1, 1, 1, 1<<12, 1<<10}}},
      {"HBDRAM_2Gb_512pin_8KB",   {1<<11,  512,  {1, 1, 1, 1<<15, 1<<7}}},
      {"HBDRAM_2Gb_512pin_4KB",   {1<<11,  512,  {1, 1, 1, 1<<16, 1<<6}}},
      {"HBDRAM_2Gb_512pin_2KB",   {1<<11,  512,  {1, 1, 1, 1<<17, 1<<5}}},

      {"HBDRAM_1Gb_256pin_32KB",   {1<<10,  256,  {1, 1, 1, 1<<12, 1<<10}}},
      {"HBDRAM_1Gb_256pin_64KB",   {1<<10,  256,  {1, 1, 1, 1<<11, 1<<11}}},
      {"HBDRAM_1Gb_256pin_8KB",   {1<<10,  256,  {1, 1, 1, 1<<14, 1<<8}}},
      {"HBDRAM_1Gb_256pin_4KB",   {1<<10,  256,  {1, 1, 1, 1<<15, 1<<7}}},
      {"HBDRAM_1Gb_256pin_2KB",   {1<<10,  256,  {1, 1, 1, 1<<16, 1<<6}}},

      {"HBDRAM_8Gb_2048pin_32KB",   {1<<13,  2048,  {1, 1, 1, 1<<15, 1<<7}}},
      {"HBDRAM_8Gb_2048pin_64KB",   {1<<13,  2048,  {1, 1, 1, 1<<14, 1<<8}}},
      {"HBDRAM_8Gb_2048pin_8KB",   {1<<13,  2048,  {1, 1, 1, 1<<17, 1<<5}}},
      {"HBDRAM_8Gb_2048pin_4KB",   {1<<13,  2048,  {1, 1, 1, 1<<18, 1<<4}}},
      {"HBDRAM_8Gb_2048pin_2KB",   {1<<13,  2048,  {1, 1, 1, 1<<19, 1<<3}}},

      {"HBDRAM_16Gb_4096pin_32KB",   {1<<14,  4096,  {1, 1, 1, 1<<16, 1<<6}}},
      {"HBDRAM_16Gb_4096pin_64KB",   {1<<14,  4096,  {1, 1, 1, 1<<15, 1<<7}}},
      {"HBDRAM_16Gb_4096pin_8KB",   {1<<14,  4096,  {1, 1, 1, 1<<18, 1<<4}}},
      {"HBDRAM_16Gb_4096pin_4KB",   {1<<14,  4096,  {1, 1, 1, 1<<19, 1<<3}}},
      {"HBDRAM_16Gb_4096pin_2KB",   {1<<14,  4096,  {1, 1, 1, 1<<20, 1<<2}}},

      {"HBDRAM_32Gb_8192pin_32KB",   {1<<15,  8192,  {1, 1, 1, 1<<17, 1<<5}}},
      {"HBDRAM_32Gb_8192pin_64KB",   {1<<15,  8192,  {1, 1, 1, 1<<16, 1<<6}}},
      {"HBDRAM_32Gb_8192pin_8KB",   {1<<15,  8192,  {1, 1, 1, 1<<19, 1<<3}}},
      {"HBDRAM_32Gb_8192pin_4KB",   {1<<15,  8192,  {1, 1, 1, 1<<20, 1<<2}}},
      {"HBDRAM_32Gb_8192pin_2KB",   {1<<15,  8192,  {1, 1, 1, 1<<21, 1<<1}}},

      // Used for cloud chip comp-bw allocation
      {"HBDRAM_1Gb_1024pin_512col",   {1<<10,  1024,  {1, 1, 1, 1<<11, 1<<9}}},
      {"HBDRAM_2Gb_1024pin_512col",   {1<<11,  1024,  {1, 1, 1, 1<<12, 1<<9}}},
      {"HBDRAM_8Gb_1024pin_512col",   {1<<13,  1024,  {1, 1, 1, 1<<14, 1<<9}}},
      {"HBDRAM_16Gb_1024pin_512col",   {1<<14,  1024,  {1, 1, 1, 1<<15, 1<<9}}},




      // Edge DRAM full space
      {"HBDRAM_2Gb_512pin_2KB_edge",   {1<<11,  512,  {1, 1, 1, 1<<17, 1<<5}}},
      {"HBDRAM_2Gb_512pin_4KB_edge",   {1<<11,  512,  {1, 1, 1, 1<<16, 1<<6}}},
      {"HBDRAM_2Gb_512pin_8KB_edge",   {1<<11,  512,  {1, 1, 1, 1<<15, 1<<7}}},
      {"HBDRAM_2Gb_512pin_16KB_edge",   {1<<11,  512,  {1, 1, 1, 1<<14, 1<<8}}},
      
      {"HBDRAM_1Gb_256pin_2KB_edge",   {1<<10,  256,  {1, 1, 1, 1<<16, 1<<6}}},
      {"HBDRAM_1Gb_256pin_4KB_edge",   {1<<10,  256,  {1, 1, 1, 1<<15, 1<<7}}},
      {"HBDRAM_1Gb_256pin_8KB_edge",   {1<<10,  256,  {1, 1, 1, 1<<14, 1<<8}}},
      {"HBDRAM_1Gb_256pin_16KB_edge",   {1<<10,  256,  {1, 1, 1, 1<<13, 1<<9}}},

      {"HBDRAM_512Mb_128pin_2KB_edge",   {1<<9,  128,  {1, 1, 1, 1<<15, 1<<7}}},
      {"HBDRAM_512Mb_128pin_4KB_edge",   {1<<9,  128,  {1, 1, 1, 1<<14, 1<<8}}},
      {"HBDRAM_512Mb_128pin_8KB_edge",   {1<<9,  128,  {1, 1, 1, 1<<13, 1<<9}}},
      {"HBDRAM_512Mb_128pin_16KB_edge",   {1<<9,  128,  {1, 1, 1, 1<<12, 1<<10}}},

      {"HBDRAM_256Mb_64pin_2KB_edge",   {1<<8,  64,  {1, 1, 1, 1<<14, 1<<8}}},
      {"HBDRAM_256Mb_64pin_4KB_edge",   {1<<8,  64,  {1, 1, 1, 1<<13, 1<<9}}},
      {"HBDRAM_256Mb_64pin_8KB_edge",   {1<<8,  64,  {1, 1, 1, 1<<12, 1<<10}}},
      {"HBDRAM_256Mb_64pin_16KB_edge",   {1<<8,  64,  {1, 1, 1, 1<<11, 1<<11}}},
    };

    inline static const std::map<std::string, std::vector<int>> timing_presets = {
      {"HBDRAM_500Mbps",  {500,   1,   1,   8,      8,      6,   17,   23,  8,   2,    1,    3,    1,     12,   -1,    2000}},
      {"HBDRAM_400Mbps",  {400,   1,   1,   7,      7,      5,   14,   19,  7,   2,    1,    3,    1,     10,   -1,    2500}},
    };


  /************************************************
   *                Organization
   ***********************************************/   
    int m_internal_prefetch_size = 1;

    inline static constexpr ImplDef m_levels = {
      "channel", "bankgroup", "bank", "row", "column",    
    };


  /************************************************
   *             Requests & Commands
   ***********************************************/
    inline static constexpr ImplDef m_commands = {
      "ACT", 
      "PRE",
      "RD",  "WR",
      "REFab"
    };

    inline static const ImplLUT m_command_scopes = LUT (
      m_commands, m_levels, {
        {"ACT",   "row"},
        {"PRE",   "bank"},
        {"RD",    "column"},  {"WR",     "column"},
        {"REFab",  "bank"},
      }
    );

    inline static const ImplLUT m_command_meta = LUT<DRAMCommandMeta> (
      m_commands, {
                // open?   close?   access?  refresh?
        {"ACT",   {true,   false,   false,   false}},
        {"PRE",   {false,  true,    false,   false}},
        {"RD",    {false,  false,   true,    false}},
        {"WR",    {false,  false,   true,    false}},
        {"REFab", {false,  false,   false,   true }},
      }
    );

    inline static constexpr ImplDef m_requests = {
      "read", "write", "all-bank-refresh"
    };

    inline static const ImplLUT m_request_translations = LUT (
      m_requests, m_commands, {
        {"read", "RD"}, {"write", "WR"}, {"all-bank-refresh", "REFab"},
      }
    );

   
  /************************************************
   *                   Timing
   ***********************************************/
    inline static constexpr ImplDef m_timings = {
      "rate", 
      "nBL", "nCL", "nRCDRD", "nRCDWR", "nRP", "nRAS", "nRC", "nWR", "nRTP", "nCWL",
      "nWTR", "nRTW",
      "nRFC", "nREFI",
      "tCK_ps"
    };


  /************************************************
   *                 Node States
   ***********************************************/
    inline static constexpr ImplDef m_states = {
       "Opened", "Closed", "N/A", "Refreshing"
    };

    inline static const ImplLUT m_init_states = LUT (
      m_levels, m_states, {
        {"channel",   "N/A"}, 
        {"bankgroup", "N/A"},
        {"bank",      "Closed"},
        {"row",       "Closed"},
        {"column",    "N/A"},
      }
    );

  public:
    struct Node : public DRAMNodeBase<HBDRAM> {
      Node(HBDRAM* dram, Node* parent, int level, int id) : DRAMNodeBase<HBDRAM>(dram, parent, level, id) {};
    };
    std::vector<Node*> m_channels;
    
    FuncMatrix<ActionFunc_t<Node>>  m_actions;
    FuncMatrix<PreqFunc_t<Node>>    m_preqs;
    FuncMatrix<RowhitFunc_t<Node>>  m_rowhits;
    FuncMatrix<RowopenFunc_t<Node>> m_rowopens;


  public:
    void tick() override {
      m_clk++;
    };

    void init() override {
      RAMULATOR_DECLARE_SPECS();
      set_organization();
      set_timing_vals();

      set_actions();
      set_preqs();
      set_rowhits();
      set_rowopens();
      
      create_nodes();
    };

    void issue_command(int command, const AddrVec_t& addr_vec) override {
      int channel_id = addr_vec[m_levels["channel"]];
      m_channels[channel_id]->update_timing(command, addr_vec, m_clk);
      m_channels[channel_id]->update_states(command, addr_vec, m_clk);
    };

    int get_preq_command(int command, const AddrVec_t& addr_vec) override {
      int channel_id = addr_vec[m_levels["channel"]];
      return m_channels[channel_id]->get_preq_command(command, addr_vec, m_clk);
    };

    bool check_ready(int command, const AddrVec_t& addr_vec) override {
      int channel_id = addr_vec[m_levels["channel"]];
      return m_channels[channel_id]->check_ready(command, addr_vec, m_clk);
    };

    bool check_rowbuffer_hit(int command, const AddrVec_t& addr_vec) override {
      int channel_id = addr_vec[m_levels["channel"]];
      return m_channels[channel_id]->check_rowbuffer_hit(command, addr_vec, m_clk);
    };
    
    bool check_node_open(int command, const AddrVec_t& addr_vec) override {
      int channel_id = addr_vec[m_levels["channel"]];
      return m_channels[channel_id]->check_node_open(command, addr_vec, m_clk);
    };

  private:
    void set_organization() {
      // Organization
      m_organization.count.resize(m_levels.size(), -1);

      // Load organization preset if provided
      if (auto preset_name = param_group("org").param<std::string>("preset").optional()) {
        if (org_presets.count(*preset_name) > 0) {
          m_organization = org_presets.at(*preset_name);
        } else {
          throw ConfigurationError("Unrecognized organization preset \"{}\" in {}!", *preset_name, get_name());
        }
      }

      // Override the preset with any provided settings
      if (auto dq = param_group("org").param<int>("dq").optional()) {
        m_organization.dq = *dq;
      }

      // Channel width
      // For hybrid bonding DRAM, channel width = DQ width
      m_channel_width = param_group("org").param<int>("channel_width").default_val(m_organization.dq);

      // Internal prefetch size
      m_internal_prefetch_size = param_group("org").param<int>("internal_prefetch_size").default_val(1);

      for (int i = 0; i < m_levels.size(); i++){
        auto level_name = m_levels(i);
        if (auto sz = param_group("org").param<int>(level_name).optional()) {
          m_organization.count[i] = *sz;
        }
      }

      if (auto density = param_group("org").param<int>("density").optional()) {
        m_organization.density = *density;
      }

      // Sanity check: is the calculated channel density the same as the provided one?
      size_t _density = size_t(m_organization.count[m_levels["bankgroup"]]) *
                        size_t(m_organization.count[m_levels["bank"]]) *
                        size_t(m_organization.count[m_levels["row"]]) *
                        size_t(m_organization.count[m_levels["column"]]) *
                        size_t(m_organization.dq) *
                        size_t(m_internal_prefetch_size);
      _density >>= 20;
      if (m_organization.density != _density) {
        throw ConfigurationError(
            "Calculated {} channel density {} Mb does not equal the provided density {} Mb!", 
            get_name(),
            _density, 
            m_organization.density
        );
      }

    };

    void set_timing_vals() {
      m_timing_vals.resize(m_timings.size(), -1);

      // Load timing preset if provided
      bool preset_provided = false;
      if (auto preset_name = param_group("timing").param<std::string>("preset").optional()) {
        if (timing_presets.count(*preset_name) > 0) {
          m_timing_vals = timing_presets.at(*preset_name);
          preset_provided = true;
        } else {
          throw ConfigurationError("Unrecognized timing preset \"{}\" in {}!", *preset_name, get_name());
        }
      }

      // Check for rate (in MT/s), and if provided, calculate and set tCK (in picosecond)
      if (auto dq = param_group("timing").param<int>("rate").optional()) {
        if (preset_provided) {
          throw ConfigurationError("Cannot change the transfer rate of {} when using a speed preset !", get_name());
        }
        m_timing_vals("rate") = *dq;
      }
      int tCK_ps = 1E6 / (m_timing_vals("rate"));
      m_timing_vals("tCK_ps") = tCK_ps;

      // Refresh timings
      // tRFC table (unit is nanosecond!)
      constexpr int tRFC_TABLE[1][7] = {
      //  0.5Gb  1Gb  2Gb  4Gb  8Gb  16Gb  32Gb
        {15, 40, 65, 90, 115, 140, 170},
      };

      // tRFEFI table (unit is nanosecond!)
      int tREFI_TABLE[4][7] = {
        //  0.5Gb  1Gb  2Gb  4Gb  8Gb  16Gb  32Gb
        {7800, 7800, 7800, 3900, 3900, 1950, 1950},
        {3900, 3900, 3900, 1950, 1950, 975, 975},
        {1950, 1950, 1950, 975, 975, 487, 487},
        {975, 975, 975, 487, 487, 243, 243},
      };

      int density_id = [](int density_Mb) -> int { 
        switch (density_Mb) {
          case 256:  return 0;
          case 512:  return 0;
          case 1024:  return 1;
          case 2048:  return 2;
          case 4096:  return 3;
          case 8192: return 4;
          case 16384: return 5;
          case 32768: return 6;
          default:    return -1;
        }
      }(m_organization.density);
      m_timing_vals("nRFC")  = JEDEC_rounding(tRFC_TABLE[0][density_id], tCK_ps);

      // load temperature (expected working temperature, used for setting nREFI) preset when provided
      m_temperature = 85;
      if (auto temperature = param_group("timing").param<int>("temperature").optional()) {
        m_temperature = *temperature;
      }
      int temperature_id = [](int temperature_Celsius) -> int {
        if(temperature_Celsius <= 85) return 0;
        if(temperature_Celsius <= 95) return 1;
        if(temperature_Celsius <= 105) return 2;
        return 3;
      }(m_temperature);
      m_timing_vals("nREFI")  = JEDEC_rounding(tREFI_TABLE[temperature_id][density_id], tCK_ps);

      // Overwrite timing parameters with any user-provided value
      // Rate and tCK should not be overwritten
      for (int i = 1; i < m_timings.size() - 1; i++) {
        auto timing_name = std::string(m_timings(i));

        if (auto provided_timing = param_group("timing").param<int>(timing_name).optional()) {
          // Check if the user specifies in the number of cycles (e.g., nRCD)
          m_timing_vals(i) = *provided_timing;
        } else if (auto provided_timing = param_group("timing").param<float>(timing_name.replace(0, 1, "t")).optional()) {
          // Check if the user specifies in nanoseconds (e.g., tRCD)
          m_timing_vals(i) = JEDEC_rounding(*provided_timing, tCK_ps);
        }
      }

      // Check if there is any uninitialized timings
      for (int i = 0; i < m_timing_vals.size(); i++) {
        if (m_timing_vals(i) == -1) {
          throw ConfigurationError("In \"{}\", timing {} is not specified!", get_name(), m_timings(i));
        }
      }      

      // Set read latency
      m_read_latency = m_timing_vals("nCL") + m_timing_vals("nBL");

      // Populate the timing constraints
      #define V(timing) (m_timing_vals(timing))
      populate_timingcons(this, {
          /*** Channel ***/ 
          /// ACT command (for row commands)
          {.level = "channel", .preceding = {"ACT"}, .following = {"ACT", "PRE", "REFab"}, .latency = 1},

          // CAS <-> CAS
          /// Data bus occupancy
          {.level = "channel", .preceding = {"RD"}, .following = {"RD"}, .latency = V("nBL")},
          {.level = "channel", .preceding = {"WR"}, .following = {"WR"}, .latency = V("nBL")},

          // CAS <-> CAS
          /// RD <-> WR, Minimum Read to Write, Assuming tWPRE = 1 tCK                          
          {.level = "channel", .preceding = {"RD"}, .following = {"WR"}, .latency = V("nCL") + V("nBL") + 2 - V("nCWL")},
          /// WR <-> RD, Minimum Read after Write
          {.level = "channel", .preceding = {"WR"}, .following = {"RD"}, .latency = V("nCWL") + V("nBL") + V("nWTR")},              
          /// RAS <-> REF
          {.level = "channel", .preceding = {"ACT"}, .following = {"REFab"}, .latency = V("nRC")},          
          {.level = "channel", .preceding = {"PRE"}, .following = {"REFab"}, .latency = V("nRP")},                  
          {.level = "channel", .preceding = {"REFab"}, .following = {"ACT"}, .latency = V("nRFC")},          

          /*** Bank ***/ 
          {.level = "bank", .preceding = {"RD"},  .following = {"PRE"}, .latency = V("nRTP")},  
          {.level = "bank", .preceding = {"ACT"}, .following = {"ACT"}, .latency = V("nRC")},  
          {.level = "bank", .preceding = {"ACT"}, .following = {"RD"}, .latency = V("nRCDRD")},  
          {.level = "bank", .preceding = {"ACT"}, .following = {"WR"}, .latency = V("nRCDWR")},  
          {.level = "bank", .preceding = {"ACT"}, .following = {"PRE"}, .latency = V("nRAS")},  
          {.level = "bank", .preceding = {"PRE"}, .following = {"ACT"}, .latency = V("nRP")},  
          {.level = "bank", .preceding = {"RD"},  .following = {"PRE"}, .latency = V("nRTP")},  
          {.level = "bank", .preceding = {"WR"},  .following = {"PRE"}, .latency = V("nCWL") + V("nBL") + V("nWR")},  
        }
      );
      #undef V

    };

    void set_actions() {
      m_actions.resize(m_levels.size(), std::vector<ActionFunc_t<Node>>(m_commands.size()));

      // Bank actions
      m_actions[m_levels["bank"]][m_commands["ACT"]] = Lambdas::Action::Bank::ACT<HBDRAM>;
      m_actions[m_levels["bank"]][m_commands["PRE"]] = Lambdas::Action::Bank::PRE<HBDRAM>;
    };

    void set_preqs() {
      m_preqs.resize(m_levels.size(), std::vector<PreqFunc_t<Node>>(m_commands.size()));

      // Channel Actions
      // TODO: change here (add a new Lambda function)
      m_preqs[m_levels["channel"]][m_commands["REFab"]] = Lambdas::Preq::Channel::RequireHBBanksClosed<HBDRAM>;

      // Bank actions
      m_preqs[m_levels["bank"]][m_commands["RD"]] = Lambdas::Preq::Bank::RequireRowOpen<HBDRAM>;
      m_preqs[m_levels["bank"]][m_commands["WR"]] = Lambdas::Preq::Bank::RequireRowOpen<HBDRAM>;
    };

    void set_rowhits() {
      m_rowhits.resize(m_levels.size(), std::vector<RowhitFunc_t<Node>>(m_commands.size()));

      m_rowhits[m_levels["bank"]][m_commands["RD"]] = Lambdas::RowHit::Bank::RDWR<HBDRAM>;
      m_rowhits[m_levels["bank"]][m_commands["WR"]] = Lambdas::RowHit::Bank::RDWR<HBDRAM>;
    }


    void set_rowopens() {
      m_rowopens.resize(m_levels.size(), std::vector<RowhitFunc_t<Node>>(m_commands.size()));

      m_rowopens[m_levels["bank"]][m_commands["RD"]] = Lambdas::RowOpen::Bank::RDWR<HBDRAM>;
      m_rowopens[m_levels["bank"]][m_commands["WR"]] = Lambdas::RowOpen::Bank::RDWR<HBDRAM>;
    }


    void create_nodes() {
      int num_channels = m_organization.count[m_levels["channel"]];
      for (int i = 0; i < num_channels; i++) {
        Node* channel = new Node(this, nullptr, 0, i);
        m_channels.push_back(channel);
      }
    };
};


}        // namespace Ramulator