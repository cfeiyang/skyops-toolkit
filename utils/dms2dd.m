function dd = dms2dd(deg, min, sec)
%DMS2DD 度分秒 -> 十进制度
%
% 输入：deg 度、min 分、sec 秒；
% 输出：dd 十进制度 = deg + min/60 + sec/3600。

dd = deg + min/60 + sec/3600;

end
