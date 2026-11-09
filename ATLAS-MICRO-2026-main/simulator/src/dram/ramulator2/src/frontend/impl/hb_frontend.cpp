#include <cmath>
#include <iostream>
#include <unordered_set>
// #include <bitset>

#include "base/request.h"
#include "base/type.h"
#include "frontend/frontend.h"
#include "addr_mapper/impl/linear_mappers.h"


namespace Ramulator {

namespace {

template <typename ReqListT, typename ReqTypeT>
void append_aligned_requests(
    ReqListT& request_list,
    Addr_t byte_addr,
    Addr_t byte_count,
    Addr_t tx_bytes,
    ReqTypeT req_type
) {
    if(byte_count <= 0) {
        return;
    }
    Addr_t aligned_addr = byte_addr - (byte_addr % tx_bytes);
    Addr_t covered_bytes = (byte_addr - aligned_addr) + byte_count;
    Addr_t req_count = static_cast<Addr_t>(std::ceil(covered_bytes * 1.0 / tx_bytes));
    for(Addr_t idx = 0; idx < req_count; ++idx) {
        request_list.emplace_back(aligned_addr + idx * tx_bytes, req_type);
    }
}

}


class HBFrontend : public IFrontEnd, public Implementation {
    RAMULATOR_REGISTER_IMPLEMENTATION(IFrontEnd, HBFrontend, "HBFrontend", "Frontend for Hybrid Bonding memory.")

public:
    void init() override {
        m_clock_ratio = param<uint>("clock_ratio").default_val(1);

        read_req_to_send = 0;
        write_req_to_send = 0;
        read_request_list.clear();
        write_request_list.clear();

        read_bytes = 0;
        write_bytes = 0;
        total_read_bytes = 0;
        total_write_bytes = 0;
    }

    void tick() override {
        if(read_req_to_send < read_request_list.size()) {
            while(true) {
                bool request_sent = m_memory_system->send(read_request_list[read_req_to_send]);
                if(request_sent)
                    read_req_to_send++;
                else
                    break;
                if(read_req_to_send >= read_request_list.size())
                    break;
            }
        }
        else if(write_req_to_send < write_request_list.size()) {
            while(true) {
                bool request_sent = m_memory_system->send(write_request_list[write_req_to_send]);
                if(request_sent)
                    write_req_to_send++;
                else
                    break;
                if(write_req_to_send >= write_request_list.size())
                    break;
            }
        }
    }

    void set_memory_system_info() override { 
        if(m_memory_system == nullptr) {
            std::cerr << "[WARNING] This frontend has not been connected to memory system." << std::endl;
            std::cerr << "          Please call this function after calling connect_memory_system" << std::endl;
            return;
        }
        channel_num = m_memory_system->get_channel_num();
        if(channel_num <= 0) {
            std::cerr << "[ERROR] Invalid channel number " << channel_num << "." << std::endl;
            exit(-1);
        }

        addr_mapper = ((LinearMapperBase*)m_memory_system->get_addr_mapper());
        if(addr_mapper == nullptr) {
            std::cerr << "[ERROR] Memory system has not set address mapper." << std::endl;
            exit(-1);
        }

        addr_mapping_type = addr_mapper->m_impl->get_name();
        if(addr_mapping_type != "OneLevelInterleave") {
            std::cerr << "[ERROR] Currently we only support OneLevelInterleave Address mapping." << std::endl;
            exit(-1);
        }
        
        Addr_t tx_offset = addr_mapper->get_tx_offset();
        if(tx_offset == -1) {
            std::cerr << "[ERROR] Invalid tx_offset value " << tx_offset << "." << std::endl;
            exit(-1);
        }
        tx_bytes = 1 << tx_offset;

        row_bits_idx = addr_mapper->m_row_bits_idx;
        col_bits_idx = addr_mapper->m_col_bits_idx;
    }

    Addr_t get_tx_bytes() override {
        return tx_bytes;
    }

    Addr_t get_ch_offset() override {
        return addr_mapper->get_ch_offset();
    }

    int send(HBInput input) override {
        read_req_to_send = 0;
        write_req_to_send = 0;
        read_request_list.clear();
        write_request_list.clear();
        read_bytes = 0;
        write_bytes = 0;

        for(auto tile: *input) {
            std::vector<Ramulator::Request>& reqeust_list = tile["is_write"] ? write_request_list : read_request_list;
            auto req_type = tile["is_write"] ? Ramulator::Request::Type::Write : Ramulator::Request::Type::Read;
            int64_t layout_rank = tile.at("layout_rank");

            std::vector<Addr_t> shape(layout_rank, 1);
            std::vector<Addr_t> strides(layout_rank, 1);
            std::vector<Addr_t> access_base(layout_rank, 0);
            std::vector<Addr_t> access_extent(layout_rank, 1);
            for(int64_t dim = 0; dim < layout_rank; ++dim) {
                shape[dim] = tile.at("shape_" + std::to_string(dim));
                strides[dim] = tile.at("stride_" + std::to_string(dim));
            }
            for(int64_t dim = 0; dim < layout_rank; ++dim) {
                access_base[dim] = tile.at("access_base_" + std::to_string(dim));
                access_extent[dim] = tile.at("access_extent_" + std::to_string(dim));
            }

            Addr_t accessed_elements = 1;
            for(int64_t dim = 0; dim < layout_rank; ++dim) {
                accessed_elements *= access_extent[dim];
            }
            if(tile["is_write"]) {
                write_bytes += accessed_elements * tile["element_size"];
            } else {
                read_bytes += accessed_elements * tile["element_size"];
            }

            std::unordered_set<Addr_t> request_addr_set;
            auto emit_legacy_contiguous_line = [&](Addr_t line_start_element_offset, Addr_t line_element_count) {
                Addr_t byte_addr = tile.at("base_addr") + line_start_element_offset * tile.at("element_size");
                Addr_t line_byte_count = line_element_count * tile.at("element_size");
                Addr_t aligned_addr = byte_addr;
                Addr_t req_count = static_cast<Addr_t>(std::ceil(line_byte_count * 1.0 / tx_bytes));
                if(byte_addr % tx_bytes != 0) {
                    aligned_addr = byte_addr - (byte_addr % tx_bytes);
                    req_count = 1 + static_cast<Addr_t>(std::ceil(line_byte_count * 1.0 / tx_bytes));
                }
                for(Addr_t idx = 0; idx < req_count; ++idx) {
                    request_addr_set.insert(aligned_addr + idx * tx_bytes);
                }
            };

            int64_t contiguous_dim = -1;
            for(int64_t dim = layout_rank - 1; dim >= 0; --dim) {
                if(strides[dim] == 1) {
                    contiguous_dim = dim;
                    break;
                }
            }

            if(contiguous_dim >= 0) {
                std::function<void(int64_t, Addr_t)> emit_line_requests =
                    [&](int64_t dim, Addr_t element_offset) {
                        if(dim == layout_rank) {
                            emit_legacy_contiguous_line(element_offset, access_extent[contiguous_dim]);
                            return;
                        }
                        if(dim == contiguous_dim) {
                            Addr_t coord = access_base[dim];
                            emit_line_requests(dim + 1, element_offset + coord * strides[dim]);
                            return;
                        }
                        for(Addr_t idx = 0; idx < access_extent[dim]; ++idx) {
                            Addr_t coord = access_base[dim] + idx;
                            emit_line_requests(dim + 1, element_offset + coord * strides[dim]);
                        }
                    };
                emit_line_requests(0, 0);
            } else {
                std::function<void(int64_t, Addr_t)> emit_requests =
                    [&](int64_t dim, Addr_t element_offset) {
                        if(dim == layout_rank) {
                            Addr_t byte_addr = tile.at("base_addr") + element_offset * tile.at("element_size");
                            Addr_t aligned_addr = byte_addr - (byte_addr % tx_bytes);
                            Addr_t covered_bytes = (byte_addr - aligned_addr) + tile.at("element_size");
                            Addr_t req_count = static_cast<Addr_t>(std::ceil(covered_bytes * 1.0 / tx_bytes));
                            for(Addr_t idx = 0; idx < req_count; ++idx) {
                                request_addr_set.insert(aligned_addr + idx * tx_bytes);
                            }
                            return;
                        }

                        for(Addr_t idx = 0; idx < access_extent[dim]; ++idx) {
                            Addr_t coord = access_base[dim] + idx;
                            emit_requests(dim + 1, element_offset + coord * strides[dim]);
                        }
                    };
                emit_requests(0, 0);
            }

            for(Addr_t req_addr : request_addr_set) {
                reqeust_list.emplace_back(req_addr, req_type);
            }
        }

        auto cmp = [this](const Ramulator::Request& r1, const Ramulator::Request& r2){
            Ramulator::Request r1_copy(r1.addr, r1.type_id);
            Ramulator::Request r2_copy(r2.addr, r2.type_id);
            
            addr_mapper->apply(r1_copy);
            addr_mapper->apply(r2_copy);
            
            for(int i=row_bits_idx; i>=1; --i) {
                if(r1_copy.addr_vec[i] != r2_copy.addr_vec[i]) {
                    return r1_copy.addr_vec[i] < r2_copy.addr_vec[i];
                }
            }

            if(r1_copy.addr_vec[col_bits_idx] != r2_copy.addr_vec[col_bits_idx]) {
                return r1_copy.addr_vec[col_bits_idx] < r2_copy.addr_vec[col_bits_idx];
            }

            return r1_copy.addr_vec[0] < r2_copy.addr_vec[0];
        };
        auto sort_and_dedup = [&](std::vector<Ramulator::Request>& list) {
            if (list.empty()) return;

            std::sort(list.begin(), list.end(), cmp);

            auto last = std::unique(
                list.begin(), 
                list.end(), 
                [](const Ramulator::Request& a, const Ramulator::Request& b) {
                    return a.addr == b.addr;
                }
            );

            list.erase(last, list.end());
        };

        sort_and_dedup(read_request_list);
        sort_and_dedup(write_request_list);

        read_bytes = read_request_list.size() * tx_bytes;
        write_bytes = write_request_list.size() * tx_bytes;
        total_read_bytes += read_bytes;
        total_write_bytes += write_bytes;
        return read_request_list.size() + write_request_list.size();
    }

    int get_read_bytes() override {
        return read_bytes;
    }

    int get_write_bytes() override {
        return write_bytes;
    }

    int get_total_read_bytes() override {
        return total_read_bytes;
    }

    int get_total_write_bytes() override {
        return total_write_bytes;
    }

    bool is_finished() override {
        bool read_req_send_finished = read_req_to_send >= read_request_list.size();
        bool write_req_send_finished = write_req_to_send >= write_request_list.size();
        return read_req_send_finished && write_req_send_finished;
    }

private:
    // memory system information, used for request generation
    int channel_num;
    LinearMapperBase* addr_mapper;
    std::string addr_mapping_type;
    Addr_t tx_bytes; // (1 << m_tx_offset, byte count per read/write command)
    int row_bits_idx;
    int col_bits_idx;

    // record for current tile's memory access
    int read_req_to_send;
    int write_req_to_send;
    std::vector<Ramulator::Request> read_request_list;
    std::vector<Ramulator::Request> write_request_list;

    // current tile's access byte count
    int read_bytes;
    int write_bytes;

    // all tiles' access byte count
    int total_read_bytes;
    int total_write_bytes;
};


}
