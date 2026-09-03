classdef STKChain
%STKCHAIN Chain 创建与结果读取

methods (Static)

    function chain = createChain(scenario, name, varargin)
    
        if numel(varargin) < 2
            error('STKChain.createChain: Chain 至少需要两个对象。');
        end
    
        % 创建 Chain
        chain = scenario.Children.New('eChain', name);
    
        % 按传入顺序添加对象
        for i = 1:numel(varargin)
            chain.Objects.AddObject(varargin{i});
        end
    
        % 计算
        chain.ComputeAccess();
        fprintf('[建链] Chain created: %s，对象数量=%d\n', name, numel(varargin));
    
    end

    % Ground -> Satellite Chain
    function chain = createSatGroundChain( scenario, name, groundNode, satellite)
    % 单站：
    %   Facility -> Satellite
    %
    % 多站：
    %   Ground Constellation -> Satellite

        chain = scenario.Children.New( 'eChain', name);

        chain.Objects.AddObject( groundNode);
        chain.Objects.AddObject( satellite);
        chain.ComputeAccess();

        fprintf( '[建链] Chain created: %s\n', name);
        fprintf( '[建链] Coverage Asset Mode = APPEND (STK 12.6 default)\n');

    end

    % Ground -> Sat(上行) -> Sat(下行) 星间中继（几何可见）
    function chain = createSatGroundChainWithISL( scenario, name, groundNode, satUpNode, satDownNode)
    % 三星带星间通信：地面站 -> 上行星 -> 星间链路 -> 下行星
    % 中间 satUpNode -> satDownNode 的 access 即星间链路（几何可见）

        chain = scenario.Children.New( 'eChain', name);

        chain.Objects.AddObject( groundNode);
        chain.Objects.AddObject( satUpNode);
        chain.Objects.AddObject( satDownNode);
        chain.ComputeAccess();

        fprintf( '[建链] Chain created (星间中继): %s\n', name);

    end

end

end
